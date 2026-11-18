"""
api/routes/trial.py — the no-sign-up trial lane: POST /trial/challenge, /trial/ticket and /trial/run/{function}

Reasoning:
- Three routes, no account (docs/plan-trial-lane-throttle.md). /challenge hands out a signed proof-of-work
  challenge; /ticket takes its solution and returns a 72 hour ticket; /run/{function} runs one whitelisted
  function for the holder of a ticket. None of them uses get_current_user, enforce_compute_rate_limit or a
  database row: the lane has its own limits (api/middleware/trial.py) and a request that is refused costs a
  few Redis reads and no Postgres write (api/middleware/usage.py records only the calls that ran).
- Every refusal (the switch off, Redis down, a spent budget, a used-up ticket, a busy task, a bad proof of
  work) is the same 429 with the same body, "trial_exhausted", which tells a first-time user to register for a
  free key: the worst case is today's flow, never a dead end. Only Retry-After differs by reason, so that a
  client backs off sensibly; it does reveal which layer refused, which the open-source code reveals anyway. Malformed requests (a bad ticket, a function that
  is not on the list, a body that is too large or does not validate) keep their own status and code.
- /run reaches a function through the domain router's own endpoint coroutine (api/routes/market_risk.py and the
  others), so the lane adds no per-function code and runs exactly what the authenticated API runs. Those
  endpoints are `async def` but call the engine synchronously, which would stall the event loop, so the lane
  runs each call in ONE worker thread per API task with a hard deadline:
  * one call at a time per task: a second one while the first is still running is refused as busy;
  * the busy flag is released when the worker thread FINISHES, not when the request gives up. A thread cannot
    be cancelled, so a call that overruns the deadline answers 504 to its caller and keeps the lane's one slot
    until it ends; the overdraft is bounded by that single slot, and the function list excludes anything whose
    cost grows with a parameter;
  * the call is charged for the milliseconds it really took (a call that hit the deadline is charged the
    deadline), never from a table of weights.
- A call that never reaches the engine (a body that fails validation, a busy task) gives its use of the ticket
  back; a call that ran, whatever it answered, does not.
- Warm-up: main.py's lifespan runs every whitelisted function once with its example body (warm_whitelist)
  before the task takes traffic, in hosted environments, so no caller pays a first-call cost against the one
  second deadline. Measured on a 4 vCPU machine, the 30 first calls together take 0.02 s once the app is
  imported, so this is cheap insurance against a lazy import, not the fix for a stall that was seen; the
  Fargate figure (0.5 vCPU) is not measured.
"""

from __future__ import annotations

import asyncio
import logging
import time
import typing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import orjson
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.routing import APIRoute
from jose import JWTError
from pydantic import BaseModel, Field, ValidationError

from api.middleware import trial as lane
from api.middleware.auth import TokenPayload
from api.middleware.rate_limit import get_trusted_client_ip
from api.middleware.trial import (
    EVENTS,
    StoreUnavailable,
    TrialRefused,
    TrialStore,
    refusal_body,
)
from api.responses import OrjsonResponse
from api.routes import (
    alm,
    credit_risk,
    derivatives,
    liquidity,
    market_risk,
    operational,
    portfolio,
    regulatory,
)
from api.tiers import policy_for
from api.trial_whitelist import EXAMPLES, WHITELIST
from config import get_settings

cfg = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trial", tags=["trial"], include_in_schema=False)

_DOMAIN_MODULES = (
    market_risk,
    credit_risk,
    liquidity,
    operational,
    portfolio,
    regulatory,
    derivatives,
    alm,
)

# The one worker thread of this API task, and whether it is busy. `_busy` is only touched from the event loop.
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pyvar-trial")
_busy = False

_TRIAL_USER = TokenPayload(sub="trial", tier="trial")


def get_store() -> TrialStore:
    """The lane's Redis store (a function so a test can replace it)."""
    return lane.get_store()


# ── the registry of whitelisted endpoints ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Entry:
    endpoint: Any
    model: type[BaseModel]
    path: str  # the domain route, relative to the API prefix, e.g. "/market-risk/kupiec_pof_test"


_registry: dict[str, _Entry] | None = None


def registry() -> dict[str, _Entry]:
    """Each whitelisted function's endpoint coroutine and request model, found on the domain routers.

    Raises:
        RuntimeError: a whitelisted name is not exactly one POST route (a rename; the suite pins this too).
    """
    global _registry
    if _registry is None:
        found: dict[str, list[_Entry]] = {name: [] for name in WHITELIST}
        for module in _DOMAIN_MODULES:
            for route in module.router.routes:
                if not isinstance(route, APIRoute) or route.methods != {"POST"}:
                    continue
                name = route.path.rsplit("/", 1)[-1]
                if name in found:
                    model = typing.get_type_hints(route.endpoint)["body"]
                    found[name].append(_Entry(route.endpoint, model, route.path))
        missing = sorted(name for name, entries in found.items() if len(entries) != 1)
        if missing:
            raise RuntimeError(f"trial whitelist names that are not one route each: {missing}")
        _registry = {name: entries[0] for name, entries in found.items()}
    return _registry


# ── running a function ───────────────────────────────────────────────────────────────────────────────────


def _run_endpoint(entry: _Entry, body: BaseModel) -> tuple[int, bytes]:
    """In the worker thread: the domain endpoint's own coroutine, run to completion on a private event loop."""
    try:
        response = asyncio.run(entry.endpoint(body=body, user=_TRIAL_USER))
    except HTTPException as exc:
        return exc.status_code, orjson.dumps({"detail": exc.detail})
    except Exception:  # noqa: BLE001 - a bug in a function must not escape the worker thread
        logger.exception("trial_function_failed")
        return 500, orjson.dumps({"detail": "The function failed unexpectedly."})
    return int(response.status_code), bytes(response.body)


def _release() -> None:
    global _busy
    _busy = False


async def _execute(entry: _Entry, body: BaseModel) -> tuple[int, bytes, float, bool]:
    """Run one call under the deadline: (status, body, milliseconds charged, timed_out)."""
    global _busy
    loop = asyncio.get_running_loop()
    _busy = True
    started = time.perf_counter()
    future = _POOL.submit(_run_endpoint, entry, body)
    # Released by the worker thread finishing, not by this request giving up (see the module docstring).
    future.add_done_callback(lambda _f: loop.call_soon_threadsafe(_release))
    wrapped = asyncio.wrap_future(future)
    wrapped.add_done_callback(
        lambda f: f.cancelled() or f.exception()
    )  # never "exception not retrieved"
    try:
        code, payload = await asyncio.wait_for(
            asyncio.shield(wrapped), timeout=cfg.trial_deadline_seconds
        )
    except TimeoutError:
        return 504, b"", cfg.trial_deadline_seconds * 1000.0, True
    return code, payload, (time.perf_counter() - started) * 1000.0, False


def warm_whitelist(budget_seconds: float = 20.0) -> int:
    """Run every whitelisted function once with its example body; returns how many answered 200.

    Called from main.py's lifespan in a thread, in hosted environments. Failures are logged, never raised: a
    function that fails here simply keeps the cold first call it would have had.
    """
    started = time.monotonic()
    ok = 0
    for name, entry in registry().items():
        if time.monotonic() - started > budget_seconds:
            logger.warning("trial_warmup_out_of_time")
            break
        try:
            code, _ = _run_endpoint(entry, entry.model.model_validate(EXAMPLES[name]))
            ok += int(code == 200)
        except Exception:  # noqa: BLE001
            logger.warning("trial_warmup_failed", extra={"function": name})
    return ok


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────────────


def _refusal_response(refusal: TrialRefused) -> Response:
    EVENTS.labels(event=f"refused_{refusal.reason}").inc()
    return OrjsonResponse(
        content=refusal_body(),
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(refusal.retry_after)},
    )


def _error(code: str, detail: str, http_status: int, event: str, **headers: str) -> Response:
    EVENTS.labels(event=event).inc()
    return OrjsonResponse(
        content={"code": code, "detail": detail}, status_code=http_status, headers=headers
    )


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


async def _read_json(request: Request, cap: int | None = None) -> Any:
    """The body as JSON, refusing one larger than `cap` (trial_max_body_bytes) without reading past it.

    Raises:
        HTTPException: 413 for a body over the cap, 422 for one that is not a JSON object.
    """
    cap = cfg.trial_max_body_bytes if cap is None else cap
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > cap:
        raise HTTPException(413, "The request body is too large.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > cap:
            raise HTTPException(413, "The request body is too large.")
        chunks.append(chunk)
    try:
        data = orjson.loads(b"".join(chunks))
    except orjson.JSONDecodeError as exc:
        raise HTTPException(422, "The body is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise HTTPException(422, "The body must be a JSON object.")
    return data


def _leaf_count(data: Any) -> int:
    """Scalars in a JSON value, counted without recursion (a cap on work, not on bytes)."""
    count = 0
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        else:
            count += 1
    return count


# ── routes ───────────────────────────────────────────────────────────────────────────────────────────────


@router.post("/challenge")
async def challenge() -> Response:
    """A proof-of-work challenge for POST /trial/ticket. Refused while the lane is off or issuance is paused."""
    store = get_store()
    try:
        controls = await store.controls()
        if not controls.on:
            raise TrialRefused("off")
        if controls.paused:
            raise TrialRefused("paused")
    except StoreUnavailable:
        return _refusal_response(TrialRefused("unavailable"))
    except TrialRefused as refusal:
        return _refusal_response(refusal)
    limits = lane.effective_limits(controls)
    return OrjsonResponse(
        content={
            "challenge": lane.new_challenge(limits.pow_bits, store.now()),
            "bits": limits.pow_bits,
            "algorithm": "sha256-leading-zero-bits",
            "expires_in": cfg.trial_pow_ttl_seconds,
        }
    )


class TicketRequest(BaseModel):
    challenge: str = Field(max_length=200)
    nonce: str = Field(max_length=32)


_TICKET_BODY_CAP = 1_024  # a challenge and a nonce are well under 300 bytes


@router.post("/ticket")
async def ticket(request: Request) -> Response:
    """Exchange a solved challenge for a trial ticket (L7, L6, L5, L4 in that order)."""
    # Read through the same capped reader as /run: a body parameter would make FastAPI read all of it first.
    try:
        body = TicketRequest.model_validate(await _read_json(request, _TICKET_BODY_CAP))
    except HTTPException as exc:
        event = "too_large" if exc.status_code == 413 else "input_error"
        return _error("trial_input_invalid", str(exc.detail), exc.status_code, event)
    except ValidationError:
        return _error(
            "trial_input_invalid", 'Send {"challenge": ..., "nonce": ...}.', 422, "input_error"
        )
    store = get_store()
    taken: list[str] = []  # counters to give back if a later layer refuses
    try:
        try:
            controls = await store.controls()
            if not controls.on:
                raise TrialRefused("off")
            if controls.paused:
                raise TrialRefused("paused")
            limits = lane.effective_limits(controls)
            await store.hourly_check(limits)
            challenge_id = lane.check_solution(
                body.challenge, body.nonce, limits.pow_bits, store.now()
            )
            if not await store.issue_ready(limits):
                raise TrialRefused("issuance")
            if not await store.consume_challenge(challenge_id):
                raise TrialRefused("pow")  # a replayed solution
            if cfg.trial_ip_counter_enabled:
                try:
                    counters = lane.ip_keys(get_trusted_client_ip(request), store.now())
                except ValueError as exc:
                    raise TrialRefused("ip") from exc
                for key, limit in counters:
                    if not await store.take_count(key, limit, lane.DAY_TTL_SECONDS):
                        raise TrialRefused("ip")
                    taken.append(key)
            asn = lane.asn_from_headers(request.headers)
            if asn is not None:
                key = store.asn_key("issue", asn)
                cap = store.asn_cap("issue", limits)
                if not await store.take_count(key, cap, lane.HOUR_TTL_SECONDS):
                    raise TrialRefused("asn")
                taken.append(key)
            outcome = await store.take_issue(limits)
            if outcome != "ok":
                retry = (
                    lane.seconds_until_utc_midnight(store.now())
                    if outcome == "daily"
                    else limits.issue_interval_ms // 1000
                )
                raise TrialRefused("issuance", retry_after=min(retry, 3600))
        except StoreUnavailable:
            raise TrialRefused("unavailable") from None
    except TrialRefused as refusal:
        for key in taken:
            await store.release_count(key)
        return _refusal_response(refusal)
    token, minted = lane.mint_ticket(store.now())
    EVENTS.labels(event="issued").inc()
    return OrjsonResponse(
        content={
            "ticket": token,
            "expires_at": minted.expires_at,
            "calls_per_day": policy_for("trial").daily_requests,
            "calls_total": cfg.trial_ticket_total_calls,
        }
    )


@router.post("/run/{function}")
async def run(function: str, request: Request) -> Response:
    """Run one whitelisted function for the holder of a trial ticket; the body is that function's request."""
    token = _bearer(request)
    if token is None:
        return _error(
            "trial_ticket_invalid",
            "A trial ticket is required: POST /api/v1/trial/ticket.",
            status.HTTP_401_UNAUTHORIZED,
            "ticket_invalid",
            **{"WWW-Authenticate": "Bearer"},
        )
    try:
        ticket_claims = lane.decode_ticket(token)
    except JWTError:
        return _error(
            "trial_ticket_invalid",
            "The trial ticket is invalid or has expired. Request a new one at POST /api/v1/trial/ticket.",
            status.HTTP_401_UNAUTHORIZED,
            "ticket_invalid",
            **{"WWW-Authenticate": "Bearer"},
        )
    # The usage middleware reads the tier from here; an allowed call is recorded as "trial".
    request.state.pyvar_tier = "trial"

    if function not in WHITELIST:
        return _error(
            "trial_function_unavailable",
            f"{function!r} is not available in the no-sign-up trial. Register for a free key to use "
            f"every function: {lane.REGISTER_URL}",
            status.HTTP_404_NOT_FOUND,
            "function_unavailable",
        )
    try:
        data = await _read_json(request)
    except HTTPException as exc:
        event = "too_large" if exc.status_code == 413 else "input_error"
        return _error("trial_input_invalid", str(exc.detail), exc.status_code, event)
    if _leaf_count(data) > cfg.trial_max_array_elements:
        return _error(
            "trial_input_too_large",
            f"A trial request may hold at most {cfg.trial_max_array_elements} values.",
            413,
            "too_large",
        )

    store = get_store()
    day_key, total_key = store.ticket_keys(ticket_claims.jti)
    counted: list[str] = []
    try:
        try:
            controls = await store.controls()
            if not controls.on:
                raise TrialRefused("off")
            limits = lane.effective_limits(controls)
            await store.hourly_check(limits)
            if not await store.compute_ready(limits):
                raise TrialRefused("compute")
            asn = lane.asn_from_headers(request.headers)
            if asn is not None and not await store.asn_has_room("compute", asn, limits):
                raise TrialRefused("asn")
            per_day = policy_for("trial").daily_requests or 0
            if not await store.take_count(day_key, per_day, lane.DAY_TTL_SECONDS):
                raise TrialRefused(
                    "ticket_quota", retry_after=lane.seconds_until_utc_midnight(store.now())
                )
            counted.append(day_key)
            if not await store.take_count(
                total_key, cfg.trial_ticket_total_calls, 72 * 3600 + 3600
            ):
                raise TrialRefused("ticket_quota", retry_after=3600)
            counted.append(total_key)
            if _busy:
                raise TrialRefused("busy")
        except StoreUnavailable:
            raise TrialRefused("unavailable") from None
        entry = registry()[function]
        try:
            model_obj = entry.model.model_validate(data)
        except ValidationError as exc:
            for key in counted:
                await store.release_count(key)
            EVENTS.labels(event="input_error").inc()
            return OrjsonResponse(
                content={
                    "detail": exc.errors(
                        include_url=False, include_context=False, include_input=False
                    )
                },
                status_code=422,
            )
    except TrialRefused as refusal:
        for key in counted:
            await store.release_count(key)
        return _refusal_response(refusal)

    code, payload, milliseconds, timed_out = await _execute(entry, model_obj)
    units = lane.units_for(milliseconds)
    await store.charge_compute(units, limits)
    if asn is not None:
        await store.add_asn_units("compute", asn, units)
    if timed_out:
        EVENTS.labels(event="timeout").inc()
        return OrjsonResponse(
            content={
                "code": "trial_timeout",
                "detail": "The function took longer than the no-sign-up trial allows. Register for a free "
                f"key to run it without that limit: {lane.REGISTER_URL}",
            },
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    EVENTS.labels(event="ran" if code == 200 else "input_error").inc()
    return Response(
        content=payload,
        status_code=code,
        media_type="application/json",
        headers={"X-Pyvar-Trial-Units": str(units)},
    )

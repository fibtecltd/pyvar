"""
api/middleware/trial.py — the no-sign-up trial lane's ticket, proof of work and shared budgets (A3)

Reasoning:
- The lane gives a first-time plugin user a few results with no registration (docs/plan-trial-lane-throttle.md).
  It hands out no API key and no account: it hands out a signed, stateless TICKET with the audience
  "pyvar-trial". python-jose refuses any token that has an `aud` at a decoder that names none, so every
  existing route (decode_token_payload in api/middleware/auth.py) refuses a ticket without a check of its own.
  The converse is NOT automatic: a decoder that names an audience still accepts a token with no `aud` at
  all, which is every session JWT. decode_ticket therefore requires the claim to be present and equal, and
  refuses a token that carries a subject or a tier, so a session JWT, an API key and a stream token are all
  refused here (tests/test_trial_ticket.py pins each).
- Everything that bounds abuse is in Redis, shared by every API task (storage/redis_client.py::redis_url()),
  and it FAILS CLOSED, the opposite of the key cache and the rate limiter: if a key cannot be read, or
  `pyvar:trial:on` is absent, the lane is off and answers 429 "trial_exhausted". The lane is a cost control
  for traffic nobody has authenticated, so "cannot tell" must mean "no". Writes that only keep books (a charge
  after a call that already ran, a refund) fail open and are counted.
- Budgets are GCRA token buckets kept in ONE key each (the key holds the "theoretical arrival time" in
  milliseconds), changed with WATCH/MULTI so two tasks never lose an update, and no Lua script: every operation
  is a single-key command, which a cluster-mode cache such as ElastiCache Serverless accepts, and the tests can
  exercise the same commands with a small in-process double. A bucket with `capacity` units and a refill of
  `n` an hour allows `capacity` units at once and then one unit every 3600/n seconds; a hard daily counter
  sits on top. The compute bucket is charged AFTER a call, for the time it really took, and may go into debt;
  a call only STARTS while the bucket holds at least `trial_min_units_to_start` units, so the overdraft is at
  most one call per API task (the lane runs one call at a time per task, api/routes/trial.py).
- Proof of work at issuance is a stateless HMAC-signed challenge, single use (the id is recorded in Redis for
  its lifetime). It only slows casual scripts; the client is open source and a native solver costs cents.
- The per-network share needs `CloudFront-Viewer-ASN`, which CloudFront adds only once the origin request
  policy forwards it (a later PR). A request without the header belongs to no network and is not capped by the
  share; the global budgets still bound it.
- The per-IP counter (L6) holds only an HMAC of the address prefix under a secret that rotates daily, in Redis
  with a 26 hour life, and is off unless `trial_ip_counter_enabled` is set. Never log it, never store it in
  Postgres.
- The breaker (L9) is evaluated by the first request of each UTC hour, so it needs no scheduler: if the
  compute or the issuance bucket is empty at three consecutive hourly checks the lane goes into attack mode
  (24-bit proof of work, a smaller per-network share), at six it pauses issuance. Both are Redis flags with a
  life of their own; `scripts/trial_ctl.py` sets and clears them.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import logging
import math
import random
import re
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from jose import JWTError, jwt
from prometheus_client import Counter
from redis.exceptions import WatchError

from api.tiers import policy_for
from config import get_settings
from storage.redis_client import redis_url

cfg = get_settings()
logger = logging.getLogger(__name__)

TRIAL_AUDIENCE = "pyvar-trial"

# Redis keys. Every key of one operation is a single key, so no operation needs one hash slot.
KEY_ON = "pyvar:trial:on"
KEY_ATTACK = "pyvar:trial:attack"
KEY_PAUSE = "pyvar:trial:pause"
KEY_BUDGET = "pyvar:trial:budget"
KEY_COMPUTE = "pyvar:trial:compute"
KEY_ISSUE = "pyvar:trial:issue"
KEY_STRIKES = "pyvar:trial:strikes"
PREFIX_DAY = "pyvar:trial:day:"  # + "compute:" or "issue:" + the UTC date
PREFIX_TICKET = "pyvar:trial:ticket:"  # + jti + ":day:" + date, or + jti + ":total"
PREFIX_POW = "pyvar:trial:pow:"  # + challenge id
PREFIX_ASN = "pyvar:trial:asn:"  # + "issue:" or "compute:" + asn + ":" + hour index
PREFIX_IP = "pyvar:trial:ip:"  # + HMAC of the prefix + ":" + date
PREFIX_CHECK = "pyvar:trial:check:"  # + hour index

DAY_TTL_SECONDS = 26 * 3600
HOUR_TTL_SECONDS = 2 * 3600
STRIKES_TTL_SECONDS = 3 * 3600  # a gap of more than this without a check resets the count
ATTACK_TTL_SECONDS = 24 * 3600
PAUSE_TTL_SECONDS = 12 * 3600
BUCKET_KEY_SLACK_MS = 60_000  # a bucket key outlives its debt by a minute
WATCH_RETRIES = 8
WATCH_BACKOFF_SECONDS = 0.002  # a conflict waits a random time up to this, doubling per retry

BUDGET_OVERRIDE_FIELDS = ("compute_hourly", "compute_daily", "issue_hourly", "issue_daily")

REGISTER_URL = "https://www.pyvar.com#get-api-key"

EVENTS = Counter(
    "pyvar_trial_events",
    "Trial-lane outcomes: issued, ran, timeout, input_error, ticket_invalid, function_unavailable, too_large, "
    "and refused_<reason> (off, unavailable, paused, pow, ip, asn, issuance, compute, ticket_quota, busy)",
    ["event"],
)
UNITS = Counter(
    "pyvar_trial_units", "Compute units charged to the trial lane (one unit is trial_unit_ms)"
)
UNRECORDED = Counter(
    "pyvar_trial_unrecorded",
    "Trial-lane bookkeeping writes that failed (a charge or a refund): a budget undercounts until it is read",
)


def record_event(event: str) -> None:
    """Count one outcome in Prometheus and, for the ones an alarm needs, write one log line.

    `issued` and every `refused_<reason>` also become a log line whose JSON key `event` is `trial_<event>`
    (the stdlib record's message; this app's structlog set-up does not render `extra=`, so the name carries the
    fact). CloudWatch metric filters in pyvar-cdk/stacks/alerts_stack.py count exactly these names, which is
    how the lane's alarms work without a Prometheus server; tests/test_trial_events.py pins the two together.
    Nothing is logged for `ran` and the other per-call outcomes: a successful call already has an `api_usage`
    row, and one line per call would only add volume.
    """
    EVENTS.labels(event=event).inc()
    if event == "issued" or event.startswith("refused_"):
        logger.info("trial_%s", event)


# Why a request was refused -> seconds to suggest in Retry-After. The body is the same for every reason.
RETRY_AFTER_SECONDS = {
    "off": 300,
    "unavailable": 60,
    "paused": 1800,
    "pow": 5,
    "ip": 3600,
    "asn": 600,
    "issuance": 360,
    "compute": 60,
    "ticket_quota": 3600,
    "busy": 2,
}


class StoreUnavailable(Exception):
    """A trial key could not be read or written (the caller fails closed)."""


class TrialRefused(Exception):
    """The lane says no. `reason` is for metrics and tests only: the client sees one body for all of them."""

    def __init__(self, reason: str, retry_after: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after if retry_after is not None else RETRY_AFTER_SECONDS[reason]


def refusal_body() -> dict[str, str]:
    """The one body every refusal carries (L2 to L9, the switch, Redis down): today's flow, never a dead end."""
    free_daily = policy_for("free").daily_requests
    return {
        "code": "trial_exhausted",
        "detail": (
            f"The no-sign-up trial is busy. A free key gives {free_daily} calls a day: register at "
            f"{REGISTER_URL} and set it in the plugin settings. The trial refills within the hour."
        ),
    }


# ── ticket ───────────────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TrialTicket:
    """What a valid ticket proves: only that this server signed it. It carries no identity and no tier."""

    jti: str
    expires_at: int


def mint_ticket(now: float | None = None) -> tuple[str, TrialTicket]:
    """Sign a ticket: `aud` "pyvar-trial", a random `jti`, a life of trial_ticket_ttl_hours, no `sub`, no tier."""
    issued = int(now if now is not None else time.time())
    expires = issued + cfg.trial_ticket_ttl_hours * 3600
    jti = secrets.token_urlsafe(16)
    payload = {"aud": TRIAL_AUDIENCE, "jti": jti, "iat": issued, "exp": expires}
    token = str(jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm))
    return token, TrialTicket(jti=jti, expires_at=expires)


_JTI = re.compile(r"[A-Za-z0-9_-]{16,64}")


def decode_ticket(token: str) -> TrialTicket:
    """Validate a ticket.

    Raises:
        JWTError: bad signature, expired, a different audience, NO audience (a session JWT), a missing or
            malformed `jti`, or a subject or tier claim (a ticket never has either).
    """
    payload = jwt.decode(
        token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm], audience=TRIAL_AUDIENCE
    )
    # python-jose accepts a token with no `aud` when the decoder names one; this lane must not.
    if payload.get("aud") != TRIAL_AUDIENCE:
        raise JWTError("Not a trial ticket")
    if "sub" in payload or "tier" in payload:
        raise JWTError("A trial ticket carries no subject and no tier")
    jti = payload.get("jti")
    if not isinstance(jti, str) or not _JTI.fullmatch(jti):
        raise JWTError("Missing or malformed ticket id")
    return TrialTicket(jti=jti, expires_at=int(payload["exp"]))


# ── proof of work ────────────────────────────────────────────────────────────────────────────────────────


def _derived_key(label: bytes) -> bytes:
    return hmac.new(cfg.jwt_secret.encode(), label, hashlib.sha256).digest()


def new_challenge(bits: int, now: float | None = None) -> str:
    """A signed challenge "<id>.<expiry>.<bits>.<signature>", valid for trial_pow_ttl_seconds."""
    issued = now if now is not None else time.time()
    body = f"{secrets.token_hex(8)}.{int(issued) + cfg.trial_pow_ttl_seconds}.{bits}"
    signature = hmac.new(_derived_key(b"pyvar-trial-pow-v1"), body.encode(), hashlib.sha256)
    return f"{body}.{signature.hexdigest()[:32]}"


def leading_zero_bits(digest: bytes) -> int:
    """How many leading zero bits `digest` has."""
    count = 0
    for byte in digest:
        if byte == 0:
            count += 8
            continue
        return count + (8 - byte.bit_length())
    return count


def solve(challenge: str, bits: int) -> str:
    """A reference solver (the tests and the documentation use it; a real client brings its own)."""
    counter = 0
    while True:
        nonce = format(counter, "x")
        digest = hashlib.sha256(f"{challenge}:{nonce}".encode()).digest()
        if leading_zero_bits(digest) >= bits:
            return nonce
        counter += 1


_NONCE = re.compile(r"[0-9A-Za-z]{1,32}")


def check_solution(challenge: str, nonce: str, required_bits: int, now: float | None = None) -> str:
    """Verify a signed challenge and its solution; returns the challenge id.

    Raises:
        TrialRefused: reason "pow", for a bad signature, an expired challenge, one issued for fewer bits than
            are required now (attack mode started after it was issued), or a wrong nonce.
    """
    current = now if now is not None else time.time()
    parts = challenge.split(".")
    if len(parts) != 4 or not _NONCE.fullmatch(nonce):
        raise TrialRefused("pow")
    cid, expiry, bits, signature = parts
    expected = hmac.new(
        _derived_key(b"pyvar-trial-pow-v1"), f"{cid}.{expiry}.{bits}".encode(), hashlib.sha256
    ).hexdigest()[:32]
    if not hmac.compare_digest(expected, signature):
        raise TrialRefused("pow")
    if not (expiry.isdigit() and bits.isdigit()) or int(expiry) < current:
        raise TrialRefused("pow")
    if int(bits) < required_bits:
        raise TrialRefused("pow")
    digest = hashlib.sha256(f"{challenge}:{nonce}".encode()).digest()
    if leading_zero_bits(digest) < int(bits):
        raise TrialRefused("pow")
    return cid


# ── request attributes ───────────────────────────────────────────────────────────────────────────────────

_ASN = re.compile(r"\d{1,10}")


def asn_from_headers(headers: Mapping[str, str]) -> str | None:
    """The viewer's network from `CloudFront-Viewer-ASN`, or None when absent or not a number."""
    raw = headers.get("cloudfront-viewer-asn", "").strip()
    return raw if _ASN.fullmatch(raw) else None


def ip_keys(client_ip: str, now: float | None = None) -> list[tuple[str, int]]:
    """The L6 counters of one address: (redis key, daily limit) for its /64 (or the address) and, for IPv6, /48.

    The key holds an HMAC of the prefix under a secret that rotates with the UTC date; nothing readable is stored.

    Raises:
        ValueError: `client_ip` is not an IP address (the caller fails closed).
    """
    moment = dt.datetime.fromtimestamp(now if now is not None else time.time(), dt.timezone.utc)
    day = moment.date().isoformat()
    secret = _derived_key(b"pyvar-trial-ip-v1|" + day.encode())
    address = ipaddress.ip_address(client_ip)
    if address.version == 4:
        prefixes = [(f"{address}", cfg.trial_ip_daily_limit)]
    else:
        prefixes = [
            (str(ipaddress.ip_network(f"{address}/64", strict=False)), cfg.trial_ip_daily_limit),
            (
                str(ipaddress.ip_network(f"{address}/48", strict=False)),
                cfg.trial_ip_v6_48_daily_limit,
            ),
        ]
    keys = []
    for prefix, limit in prefixes:
        digest = hmac.new(secret, prefix.encode(), hashlib.sha256).hexdigest()[:32]
        keys.append((f"{PREFIX_IP}{digest}:{day}", limit))
    return keys


# ── limits and the control keys ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Controls:
    """The switches and overrides read from Redis in one round trip."""

    on: bool
    attack: bool
    paused: bool
    budget: dict[str, int]


@dataclass(frozen=True)
class Limits:
    """The budgets in force right now: the settings, lowered (never raised) by `pyvar:trial:budget`."""

    compute_capacity: int
    compute_refill_hour: int
    compute_daily: int
    issue_capacity: int
    issue_refill_hour: int
    issue_daily: int
    asn_share: float
    pow_bits: int

    @property
    def compute_interval_ms(self) -> int:
        return _interval_ms(self.compute_refill_hour)

    @property
    def issue_interval_ms(self) -> int:
        return _interval_ms(self.issue_refill_hour)


def _interval_ms(refill_per_hour: int) -> int:
    """Milliseconds to refill one unit; a refill of 0 gives an interval no bucket can ever repay."""
    return 3_600_000 // refill_per_hour if refill_per_hour > 0 else 10**12


def parse_budget_override(raw: str | None) -> dict[str, int]:
    """The override JSON as non-negative ints for the known fields; anything else is ignored, with a warning."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        return {
            name: max(0, int(data[name]))
            for name in BUDGET_OVERRIDE_FIELDS
            if isinstance(data.get(name), int) and not isinstance(data.get(name), bool)
        }
    except (ValueError, TypeError):
        logger.warning("trial_budget_override_ignored")
        return {}


def _lowered(setting: int, override: int | None) -> int:
    """The setting, or the override when it is lower: an override can only tighten a budget, never loosen it."""
    return setting if override is None else min(setting, override)


def effective_limits(controls: Controls) -> Limits:
    """The settings, lowered by the override; attack mode adds the stricter proof of work and network share."""
    override = controls.budget
    return Limits(
        compute_capacity=_lowered(cfg.trial_compute_capacity_units, override.get("compute_hourly")),
        compute_refill_hour=_lowered(
            cfg.trial_compute_refill_per_hour, override.get("compute_hourly")
        ),
        compute_daily=_lowered(cfg.trial_compute_daily_units, override.get("compute_daily")),
        issue_capacity=_lowered(cfg.trial_issue_capacity, override.get("issue_hourly")),
        issue_refill_hour=_lowered(cfg.trial_issue_refill_per_hour, override.get("issue_hourly")),
        issue_daily=_lowered(cfg.trial_issue_daily, override.get("issue_daily")),
        asn_share=cfg.trial_asn_share_attack if controls.attack else cfg.trial_asn_share,
        pow_bits=cfg.trial_pow_bits_attack if controls.attack else cfg.trial_pow_bits,
    )


def bucket_level(tat_ms: int, interval_ms: int, capacity_units: int, now_ms: int) -> int:
    """Units a bucket would grant right now: capacity minus the debt that has not yet refilled."""
    debt = max(0, tat_ms - now_ms)
    return max(0, (capacity_units * interval_ms - debt) // interval_ms)


def units_for(milliseconds: float) -> int:
    """The charge of a call: ceil(ms / trial_unit_ms), at least one unit."""
    return max(1, math.ceil(milliseconds / cfg.trial_unit_ms))


def utc_date(now: float) -> str:
    return dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()


def seconds_until_utc_midnight(now: float) -> int:
    moment = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    midnight = (moment + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - moment).total_seconds()))


def _build_client() -> Any:
    """The async Redis client, tuned like api/assistant/store.py's (idle-connection checks, short retry)."""
    import redis.asyncio as aioredis
    from redis.asyncio.retry import Retry
    from redis.backoff import ExponentialBackoff
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError

    return aioredis.from_url(
        redis_url(),
        decode_responses=True,
        socket_keepalive=True,
        health_check_interval=30,
        retry=Retry(ExponentialBackoff(cap=0.2, base=0.02), retries=2),
        retry_on_error=[RedisConnectionError, RedisTimeoutError],
    )


class TrialStore:
    """Every Redis operation of the lane. `client` is any async Redis-like object (a test passes a double)."""

    def __init__(self, client: Any | None = None, clock: Callable[[], float] = time.time) -> None:
        self._client = client
        self._clock = clock
        self._checked_hour = -1  # the last UTC hour this task tried the breaker check

    def now(self) -> float:
        return self._clock()

    def _redis(self) -> Any:
        if self._client is None:
            self._client = _build_client()
        return self._client

    # -- switches ----------------------------------------------------------------------------------------

    async def controls(self) -> Controls:
        """The four control keys in one round trip.

        Raises:
            StoreUnavailable: a key could not be read. The caller treats the lane as off.
        """
        try:
            async with self._redis().pipeline(transaction=False) as pipe:
                for key in (KEY_ON, KEY_ATTACK, KEY_PAUSE, KEY_BUDGET):
                    pipe.get(key)
                on, attack, paused, budget = await pipe.execute()
        except Exception as exc:  # noqa: BLE001 - any failure means "cannot tell"
            raise StoreUnavailable(type(exc).__name__) from exc
        return Controls(
            on=on is not None,
            attack=attack is not None,
            paused=paused is not None,
            budget=parse_budget_override(budget),
        )

    # -- primitives --------------------------------------------------------------------------------------

    async def _get_int(self, key: str) -> int:
        raw = await self._redis().get(key)
        return int(raw) if raw else 0

    async def _incr(self, key: str, amount: int, ttl_seconds: int) -> int:
        async with self._redis().pipeline(transaction=True) as pipe:
            pipe.incrby(key, amount)
            pipe.expire(key, ttl_seconds)
            result = await pipe.execute()
        return int(result[0])

    async def _decr(self, key: str, amount: int = 1) -> None:
        """Give back a count. Fails open: a counter left high only makes the lane stricter."""
        try:
            await self._redis().decrby(key, amount)
        except Exception:  # noqa: BLE001
            UNRECORDED.inc()
            logger.warning("trial_refund_not_recorded")

    async def _bucket_take(
        self,
        key: str,
        units: int,
        interval_ms: int,
        capacity_units: int,
        now_ms: int,
        overdraft: bool,
    ) -> bool:
        """Add `units` to a GCRA bucket. Without `overdraft`, refuse when it would exceed the capacity."""
        cost = units * interval_ms
        capacity_ms = capacity_units * interval_ms
        async with self._redis().pipeline(transaction=True) as pipe:
            for attempt in range(WATCH_RETRIES):
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    # Never earlier than now: an idle bucket does not store credit.
                    tat = max(int(raw) if raw else 0, now_ms)
                    new_tat = tat + cost
                    if not overdraft and new_tat - now_ms > capacity_ms:
                        await pipe.unwatch()
                        return False
                    pipe.multi()
                    pipe.set(key, new_tat, px=new_tat - now_ms + BUCKET_KEY_SLACK_MS)
                    await pipe.execute()
                    return True
                except WatchError:
                    await pipe.reset()
                    # Another task wrote the key first. Wait a random, growing moment so that the losers do
                    # not collide again in lockstep (without it, 30 simultaneous callers mostly gave up).
                    await asyncio.sleep(
                        random.random() * WATCH_BACKOFF_SECONDS * 2**attempt
                    )  # nosec B311
        raise StoreUnavailable("contention")

    async def _bucket_level(
        self, key: str, interval_ms: int, capacity_units: int, now_ms: int
    ) -> int:
        return bucket_level(await self._get_int(key), interval_ms, capacity_units, now_ms)

    # -- compute budget (L3) -----------------------------------------------------------------------------

    def _day_key(self, kind: str, now: float) -> str:
        return f"{PREFIX_DAY}{kind}:{utc_date(now)}"

    async def compute_ready(self, limits: Limits) -> bool:
        """True while a call may start: at least trial_min_units_to_start units in the bucket and in the day.

        Raises:
            StoreUnavailable: the budget could not be read.
        """
        now = self.now()
        need = cfg.trial_min_units_to_start
        try:
            level = await self._bucket_level(
                KEY_COMPUTE, limits.compute_interval_ms, limits.compute_capacity, int(now * 1000)
            )
            used = await self._get_int(self._day_key("compute", now))
        except Exception as exc:  # noqa: BLE001
            raise StoreUnavailable(type(exc).__name__) from exc
        return level >= need and used + need <= limits.compute_daily

    async def charge_compute(self, units: int, limits: Limits) -> None:
        """Charge a call that has run. The bucket may go into debt. Fails open and counts the miss."""
        now = self.now()
        try:
            await self._bucket_take(
                KEY_COMPUTE,
                units,
                limits.compute_interval_ms,
                limits.compute_capacity,
                int(now * 1000),
                overdraft=True,
            )
            await self._incr(self._day_key("compute", now), units, DAY_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            UNRECORDED.inc()
            logger.warning("trial_charge_not_recorded", extra={"units": units})
        UNITS.inc(units)

    # -- issuance budget (L4) ----------------------------------------------------------------------------

    async def issue_ready(self, limits: Limits) -> bool:
        """Read-only: one ticket could be issued now (bucket and day)."""
        now = self.now()
        try:
            level = await self._bucket_level(
                KEY_ISSUE, limits.issue_interval_ms, limits.issue_capacity, int(now * 1000)
            )
            used = await self._get_int(self._day_key("issue", now))
        except Exception as exc:  # noqa: BLE001
            raise StoreUnavailable(type(exc).__name__) from exc
        return level >= 1 and used < limits.issue_daily

    async def take_issue(self, limits: Limits) -> str:
        """Take one ticket from the day and the bucket: "ok", "daily" or "bucket" (what ran out).

        Raises:
            StoreUnavailable: the budget could not be read or written.
        """
        now = self.now()
        day_key = self._day_key("issue", now)
        try:
            used = await self._incr(day_key, 1, DAY_TTL_SECONDS)
            if used > limits.issue_daily:
                await self._decr(day_key)
                return "daily"
            took = await self._bucket_take(
                KEY_ISSUE,
                1,
                limits.issue_interval_ms,
                limits.issue_capacity,
                int(now * 1000),
                overdraft=False,
            )
            if not took:
                await self._decr(day_key)
                return "bucket"
        except StoreUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StoreUnavailable(type(exc).__name__) from exc
        return "ok"

    # -- counters ----------------------------------------------------------------------------------------

    async def take_count(self, key: str, limit: int, ttl_seconds: int) -> bool:
        """Count one use of `key`; False (and no count) when it would exceed `limit`."""
        try:
            used = await self._incr(key, 1, ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            raise StoreUnavailable(type(exc).__name__) from exc
        if used > limit:
            await self._decr(key)
            return False
        return True

    async def release_count(self, key: str) -> None:
        await self._decr(key)

    async def consume_challenge(self, challenge_id: str) -> bool:
        """Record a challenge id as used; False if it already was (a replayed solution)."""
        try:
            first = await self._redis().set(
                f"{PREFIX_POW}{challenge_id}", "1", nx=True, ex=cfg.trial_pow_ttl_seconds + 10
            )
        except Exception as exc:  # noqa: BLE001
            raise StoreUnavailable(type(exc).__name__) from exc
        return bool(first)

    def ticket_keys(self, jti: str) -> tuple[str, str]:
        """(today's counter, lifetime counter) of one ticket."""
        return (
            f"{PREFIX_TICKET}{jti}:day:{utc_date(self.now())}",
            f"{PREFIX_TICKET}{jti}:total",
        )

    # -- per-network share (L5) --------------------------------------------------------------------------

    def asn_key(self, kind: str, asn: str) -> str:
        return f"{PREFIX_ASN}{kind}:{asn}:{int(self.now() // 3600)}"

    @staticmethod
    def asn_cap(kind: str, limits: Limits) -> int:
        hourly = limits.issue_refill_hour if kind == "issue" else limits.compute_refill_hour
        return max(1, int(limits.asn_share * hourly))

    async def asn_has_room(self, kind: str, asn: str, limits: Limits) -> bool:
        """Read-only: this network has not yet used its share of the hour."""
        try:
            used = await self._get_int(self.asn_key(kind, asn))
        except Exception as exc:  # noqa: BLE001
            raise StoreUnavailable(type(exc).__name__) from exc
        return used < self.asn_cap(kind, limits)

    async def add_asn_units(self, kind: str, asn: str, units: int) -> None:
        try:
            await self._incr(self.asn_key(kind, asn), units, HOUR_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            UNRECORDED.inc()

    # -- breaker (L9) ------------------------------------------------------------------------------------

    async def hourly_check(self, limits: Limits) -> None:
        """Once per UTC hour, by whichever request comes first: count an empty budget, trip the breaker.

        Bookkeeping, so any failure is swallowed (the request that triggered it must not suffer). Each API
        task tries once an hour; the Redis key decides which task's check counts.
        """
        now = self.now()
        hour = int(now // 3600)
        if hour == self._checked_hour:
            return
        self._checked_hour = hour
        try:
            client = self._redis()
            first = await client.set(f"{PREFIX_CHECK}{hour}", "1", nx=True, ex=HOUR_TTL_SECONDS)
            if not first:
                return
            compute_empty = not await self._compute_has_units(limits, now)
            issue_empty = not await self.issue_ready(limits)
            if not (compute_empty or issue_empty):
                await client.delete(KEY_STRIKES)
                return
            strikes = await self._incr(KEY_STRIKES, 1, STRIKES_TTL_SECONDS)
            # One log line per state change (an alarm counts them; see record_event). The strike line comes
            # first so a trip reads as strike, then what it set.
            logger.warning("trial_breaker_strike", extra={"strikes": strikes})
            if strikes >= cfg.trial_breaker_pause_after:
                await client.set(KEY_PAUSE, "1", ex=PAUSE_TTL_SECONDS)
                logger.warning("trial_breaker_pause")
            if strikes >= cfg.trial_breaker_attack_after:
                await client.set(KEY_ATTACK, "1", ex=ATTACK_TTL_SECONDS)
                logger.warning("trial_breaker_attack")
        except Exception:  # noqa: BLE001
            logger.warning("trial_breaker_check_failed")

    async def _compute_has_units(self, limits: Limits, now: float) -> bool:
        level = await self._bucket_level(
            KEY_COMPUTE, limits.compute_interval_ms, limits.compute_capacity, int(now * 1000)
        )
        used = await self._get_int(self._day_key("compute", now))
        return level >= cfg.trial_min_units_to_start and used < limits.compute_daily


_store: TrialStore | None = None


def get_store() -> TrialStore:
    """The process-wide store, built on first use."""
    global _store
    if _store is None:
        _store = TrialStore()
    return _store

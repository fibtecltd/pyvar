"""
api/middleware/rate_limit.py — tier-aware request-frequency throttling (#146)

Reasoning:
- slowapi has been referenced in docstrings/README/the AMI bake since P6 but
  never actually wired in (issue #146) — this is that wiring.
- Backend: Redis-backed (limits.storage.RedisStorage, which slowapi's Limiter
  wraps), pointed at the SAME ElastiCache cluster Celery/api/routes/caching.py
  already use (storage/redis_client.py::redis_url()). slowapi's default
  in-memory storage is a non-starter here: pyvar-cdk/config.py sets
  api_min_tasks=2 in every real environment, so each Fargate task would track
  limits independently and a client could get ~api_max_tasks x the intended
  quota just from load-balancer luck.
- Scope: main.py wires 9 route groups under /api/v1 (var_router + 8
  auto-generated domain routers — 386 individual endpoints total, one per
  engine function, per scripts/gen_p3.py's header comment). Decorating each of
  those 386 hand-generated functions with @limiter.limit(...) is impractical,
  and slowapi's own default_limits mechanism doesn't help either: reading
  slowapi/extension.py, a default_limits entry gets scope=None, and
  __evaluate_limits falls back to `limit_scope = lim.scope or endpoint` — so a
  naive default_limits=["10/day"] would give EACH of the 386 endpoints its own
  separate bucket (a free user could hit ~3,860 requests/day total), not the
  single account-wide quota the design calls for.
- So: this module builds a plain FastAPI dependency instead of using slowapi's
  decorator sugar, calling Limiter's public `.limiter` property (the
  underlying `limits` RateLimiter strategy) directly with a FIXED scope
  string ("compute") shared across every endpoint. That fixed scope is what
  turns 386 separate routes into one combined per-account daily bucket.
  main.py applies it via `include_router(..., dependencies=[Depends(...)])` —
  zero changes to any of the 8 generated domain files.
- enforce_compute_rate_limit declares its own `Depends(get_current_user)`.
  Every one of the 386 endpoints already takes that same dependency itself;
  FastAPI caches dependency results per request by default, so this does NOT
  cause a second JWT decode on top of the one each endpoint already pays for.
- enforce_public_rate_limit (for api/routes/public_data.py's two unauthenticated
  endpoints) is IP-keyed. The app sits behind ALB + CloudFront, and
  pyvar-cdk/stacks/api_stack.py's ALB listener enforces X-Origin-Verify (a
  shared secret only CloudFront knows) — any request that reaches the ALB
  directly, bypassing CloudFront, is rejected with 403. That guarantee means
  the X-Forwarded-For chain reaching this app always has CloudFront's hop
  appended, then the ALB's own hop appended after that — so the trustworthy
  client IP is the SECOND-TO-LAST entry (the last is CloudFront's own edge
  IP; anything before is client-suppliable and spoofable). Plain
  slowapi.util.get_remote_address (raw socket peer = the ALB itself) and
  get_ipaddr (trusts the whole raw header) are both wrong here —
  get_trusted_client_ip() below implements the correct 2-hop trust boundary.
- Fail-open on a Redis/storage error (log + allow): rate limiting here is an
  anti-abuse/cost-control measure, not the auth boundary — an ElastiCache
  blip must not turn into "no user can compute anything." Same philosophy
  already used for tasks/var_task.py's _emit_job_metric and
  api/routes/caching.py's cache reads/writes.
- Tiers: "enterprise" and "internal" are unconditionally exempt. "internal" is
  the service JWT pyvar-cdk/lambda/public_data_publisher/handler.py mints
  every 15 minutes to refresh the homepage demo — kept distinct from
  "enterprise" (rather than reusing it) so that scheduled job's calls don't
  pollute real customer-tier usage analytics in api_usage/var_jobs.
"""

from __future__ import annotations

import logging
import time

import limits
from fastapi import Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.middleware.auth import TokenPayload, get_current_user
from config import get_settings
from storage.redis_client import redis_url

cfg = get_settings()
logger = logging.getLogger(__name__)

_EXEMPT_TIERS = {"enterprise", "internal"}

# One shared Limiter for both authenticated and unauthenticated checks — its
# key_func is only used if slowapi's own decorator API is ever reached for,
# which this module deliberately doesn't do (see module docstring); every
# call site below passes its own identifiers straight to `.limiter.hit(...)`.
# Construction is safe at import time: redis.from_url() (which RedisStorage
# calls internally) builds a lazy connection pool — no socket I/O happens
# until the first .hit()/.get_window_stats() call, same as
# storage/session.py's lazy async engine.
_limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=redis_url(),
    key_prefix="pyvar-ratelimit",
)


def get_trusted_client_ip(request: Request) -> str:
    """The real client IP, trusting exactly the CloudFront+ALB double hop.

    See module docstring for why index -2 (not -1, not the raw header as a
    whole) is the correct trust boundary for this specific topology. Falls
    back to the direct connection peer when there are fewer than 2 hops —
    correct for local dev, tests, or any request that didn't come through
    the expected proxy chain.
    """
    forwarded_for = request.headers.get("x-forwarded-for", "")
    hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
    if len(hops) >= 2:
        return hops[-2]
    return get_remote_address(request)


def _raise_rate_limited(item: limits.RateLimitItem, *identifiers: str) -> None:
    retry_after = 60
    try:
        reset_at, _remaining = _limiter.limiter.get_window_stats(item, *identifiers)
        retry_after = max(1, int(reset_at - time.time()))
    except Exception:  # noqa: BLE001 — best-effort Retry-After, 429 still fires either way
        logger.warning("Failed to compute Retry-After for rate limit response")

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Please retry later.",
        headers={"Retry-After": str(retry_after)},
    )


async def enforce_compute_rate_limit(
    request: Request,
    user: TokenPayload = Depends(get_current_user),
) -> None:
    """Account-wide daily quota across every /api/v1 compute endpoint.

    Applied via `include_router(..., dependencies=[Depends(enforce_compute_rate_limit)])`
    in main.py for var_router and each of the 8 domain routers — see module
    docstring for why a fixed "compute" scope (not per-endpoint) is what
    makes this one shared bucket per user rather than 386 separate ones.
    """
    if user.tier in _EXEMPT_TIERS:
        return

    daily_cap = cfg.rate_limit_pro_daily if user.tier == "pro" else cfg.rate_limit_free_daily
    item = limits.parse(f"{daily_cap}/day")

    try:
        allowed = _limiter.limiter.hit(item, user.user_id, "compute")
    except Exception:  # noqa: BLE001 — fail open on a Redis outage, see module docstring
        logger.warning("Rate limit storage unavailable — allowing request", exc_info=True)
        return

    if not allowed:
        _raise_rate_limited(item, user.user_id, "compute")


async def enforce_public_rate_limit(request: Request) -> None:
    """Per-IP hourly quota for the two unauthenticated /public/* endpoints."""
    client_ip = get_trusted_client_ip(request)
    item = limits.parse(f"{cfg.rate_limit_unauth_per_hour}/hour")

    try:
        allowed = _limiter.limiter.hit(item, client_ip, "public")
    except Exception:  # noqa: BLE001 — fail open on a Redis outage, see module docstring
        logger.warning("Rate limit storage unavailable — allowing request", exc_info=True)
        return

    if not allowed:
        _raise_rate_limited(item, client_ip, "public")


async def enforce_register_rate_limit(request: Request) -> None:
    """Per-IP hourly quota for POST /auth/register.

    Registration is unauthenticated (there's no JWT yet to key off), so this
    is IP-keyed like enforce_public_rate_limit rather than user-keyed like
    enforce_compute_rate_limit — and uses its own "register" scope so it
    can't share or exhaust the /public/* bucket a client behind the same IP
    might also be using. Closes the gap noted when this endpoint's own
    anti-abuse gap was reviewed: registration previously had no throttling
    at all, so an attacker could spam SES sends (cost + reputation risk) or
    probe the disposable-email blocklist (api/middleware/disposable_email.py)
    without limit.
    """
    client_ip = get_trusted_client_ip(request)
    item = limits.parse(f"{cfg.rate_limit_register_per_hour}/hour")

    try:
        allowed = _limiter.limiter.hit(item, client_ip, "register")
    except Exception:  # noqa: BLE001 — fail open on a Redis outage, see module docstring
        logger.warning("Rate limit storage unavailable — allowing request", exc_info=True)
        return

    if not allowed:
        _raise_rate_limited(item, client_ip, "register")

---
name: pyvar-arch-api-gateway
description: >
  Activate when building or modifying pyvar's API gateway layer: FastAPI
  route design, Pydantic request/response models, JWT authentication,
  rate limiting, orjson serialisation, or OpenAPI schema generation.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [fastapi, pydantic, JWT, orjson, rate-limiting, OpenAPI, CORS,
       middleware, authentication, api-gateway]
---

# pyvar — Architecture: API Gateway

## Stack
| Component | Role |
|---|---|
| **FastAPI** | Async HTTP framework, OpenAPI auto-docs |
| **Pydantic v2** | Request validation, response serialisation |
| **JWT (python-jose)** | Subscriber authentication & token refresh |
| **orjson** | High-performance JSON (3-10x faster than stdlib) |
| **Rate limiting** | slowapi / redis-py sliding window per subscriber |

## Route conventions
```python
# Each of the 8 domain routers (market-risk, credit-risk, liquidity, operational,
# portfolio, regulatory, derivatives, alm) is POST-only: one auto-generated
# endpoint per engine function (scripts/gen_p3.py), no GET-sync variant and no
# "/async" suffix — every one of the 386 endpoints dispatches synchronously and
# returns the computed result directly (these are fast engine calls, not queued
# jobs). Only VaR uses the async job pattern, and it is its own two-route pair,
# not a generic convention applied domain-wide:
POST /api/v1/var/compute                 # 202, dispatches Celery, returns task_id
GET  /api/v1/var/result/{task_id}        # poll job status + result

POST /api/v1/market-risk/historical_simulation_var   # sync, returns result directly
POST /api/v1/derivatives/black_scholes_european_option
```

## Pydantic models pattern
```python
# Pydantic v2 — field_validator + Annotated[Field(...)], not the v1 `validator`
# decorator / `class Config` pattern. orjson is NOT wired through Pydantic's
# Config at all in this codebase; it's applied once, globally, via
# api/responses.py's OrjsonResponse (FastAPI's default_response_class) — see
# below. Mirrors schemas/var.py's actual VaRRequest/VaRResult.
from typing import Annotated
from pydantic import BaseModel, Field, field_validator

class VaRRequest(BaseModel):
    portfolio_value: Annotated[float, Field(gt=0)]
    returns: Annotated[list[float], Field(min_length=30, max_length=10_000)]
    confidence_level: Annotated[float, Field(gt=0.0, lt=1.0, default=0.99)] = 0.99
    horizon_days: Annotated[int, Field(ge=1, le=250, default=1)] = 1
    n_simulations: Annotated[int, Field(ge=1_000, le=500_000, default=10_000)] = 10_000

    @field_validator("confidence_level")
    @classmethod
    def confidence_must_be_standard(cls, v: float) -> float:
        if not (0.90 <= v <= 0.9999):
            raise ValueError(f"Confidence level {v} outside [0.90, 0.9999]")
        return v

class VaRResult(BaseModel):
    var_pct: float
    var_abs: float
    cvar_pct: float
    cvar_abs: float
    loss_dist: list[float]  # empty + presigned_url populated above the S3 offload threshold
```

## orjson serialisation — applied once, at the response layer
```python
# api/responses.py — NOT per-schema Config. Set as FastAPI's
# default_response_class in main.py's create_app(), so every route gets it
# automatically without per-route decoration.
import orjson
from fastapi.responses import JSONResponse

class OrjsonResponse(JSONResponse):
    def render(self, content: object) -> bytes:
        return orjson.dumps(
            content,
            option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS | orjson.OPT_UTC_Z,
        )
```

## JWT middleware
```python
# api/middleware/auth.py — HTTPBearer + python-jose, not OAuth2PasswordBearer
# (there is no token-issuing /auth/token OAuth2 flow; auth.py mints JWTs from
# a plain email/password register+login pair instead).
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

bearer_scheme = HTTPBearer()

class TokenPayload:
    def __init__(self, sub: str, tier: str = "free"):
        self.user_id = sub
        self.tier = tier  # free | pro | enterprise | internal
        self.max_simulations = {
            "free": 10_000, "pro": 100_000, "enterprise": 500_000, "internal": 500_000,
        }.get(tier, 10_000)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> TokenPayload:
    try:
        payload = jwt.decode(credentials.credentials, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
        return TokenPayload(sub=payload["sub"], tier=payload.get("tier", "free"))
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
```
`"internal"` is a distinct tier from `"enterprise"` — it's the service JWT
`pyvar-cdk/lambda/public_data_publisher/handler.py` mints every 15 minutes to
refresh the homepage demo, kept separate so its calls don't pollute real
customer-tier usage analytics.

## Rate limiting — account-wide daily quota, not per-minute per tier
```python
# api/middleware/rate_limit.py (#146). NOT "100/min Standard, 1000/min Pro" —
# the real limits are a per-user DAILY quota shared across every one of the
# 386 compute endpoints, configured in config.py:
#   free tier:        cfg.rate_limit_free_daily   = 10/day
#   pro tier:          cfg.rate_limit_pro_daily     = 500/day
#   enterprise/internal: unconditionally exempt
#   unauthenticated /public/*: cfg.rate_limit_unauth_per_hour = 5/hour, per IP
#
# Backend: Redis-backed (limits.storage.RedisStorage, the same ElastiCache
# Serverless cluster as storage/redis_client.py::redis_url()) — NOT slowapi's
# default in-memory storage, which would track limits independently per
# Fargate task (api_min_tasks=2+) and let a client get ~N x the intended quota
# from load-balancer luck alone.
#
# slowapi's decorator sugar (@limiter.limit(...)) is NOT used per-route either:
# with 386 hand-generated endpoints, slowapi's default_limits mechanism gives
# EACH endpoint its own separate bucket (scope=None falls back to the endpoint
# name), turning "10/day" into ~3,860 requests/day account-wide. Instead this
# module calls the underlying `limits` RateLimiter directly with a fixed
# scope string ("compute") shared by every endpoint, applied once via
# `include_router(..., dependencies=[Depends(enforce_compute_rate_limit)])`.
#
# Fail-open on a Redis outage (log + allow) — rate limiting is an
# anti-abuse/cost control, not the auth boundary.
```

### Production lesson: CloudFront alias uniqueness is ACCOUNT-WIDE
CloudFront enforces alias (custom domain) uniqueness across the *entire AWS
account*, not per-distribution. `pyvar-cdk/stacks/edge_stack.py`'s
distribution reads its aliases from `cfg.edge_domain_names`
(`pyvar-cdk/config.py`) — dev already claims `["pyvar.com", "www.pyvar.com"]`
for its live distribution, so prod's `EdgeStack` cannot claim them too: its
first deploy would fail on the alias collision. The fix was giving prod
`edge_domain_names=[]` — it serves its bare `*.cloudfront.net` address with
CloudFront's default certificate until a deliberate domain cutover, rather
than fighting dev for the same alias. When `edge_domain_names` is empty, no
ACM certificate is provisioned and `minimum_protocol_version=TLS_V1_2_2021`
is silently *not* enforced (CloudFront falls back to its default cert's fixed
TLS policy) — acceptable only because nothing points real traffic at that
distribution's default domain yet.

### Production lesson: SES has the identical per-domain, account-wide collision
`pyvar-cdk/stacks/ses_stack.py` verifies an SES `EmailIdentity` used to send
account-verification email (`api/routes/auth.py`). SES allows only one
`EmailIdentity` per literal domain per account+region — dev's `SesStack`
verified `pyvar.com` itself, so prod's first deploy failed with
`"EmailIdentity ... pyvar.com already exists"`. Fixed the same way as the
CloudFront case: `cfg.ses_domain_name` defaults to `pyvar.com` but prod
overrides it to `mail.pyvar.com`, a distinct identity dev never touches.

## Dependencies
fastapi >= 0.111 · pydantic >= 2.0 · orjson >= 3.9
python-jose >= 3.3 · slowapi >= 0.1 · uvicorn >= 0.29

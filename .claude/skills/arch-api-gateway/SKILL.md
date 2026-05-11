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
# Domain routes follow this pattern:
GET  /api/v1/{domain}/{function}          # sync (fast)
POST /api/v1/{domain}/{function}/async    # returns task_id for Celery
GET  /api/v1/tasks/{task_id}/status      # poll job status
GET  /api/v1/tasks/{task_id}/result      # retrieve result

# Example:
POST /api/v1/market-risk/historical_simulation_var
POST /api/v1/derivatives/black_scholes_european_option/async
```

## Pydantic models pattern
```python
from pydantic import BaseModel, Field, validator
import orjson

class VaRRequest(BaseModel):
    returns: list[float]
    confidence: float = Field(0.99, ge=0.90, le=0.9999)
    horizon: int = Field(1, ge=1, le=250)
    simulations: int = Field(10_000, ge=1_000, le=1_000_000)

    class Config:
        json_loads = orjson.loads
        json_dumps = lambda v, *, default: orjson.dumps(v, default=default).decode()

class VaRResponse(BaseModel):
    var: float
    confidence: float
    horizon: int
    method: str
    computation_time_ms: float
```

## JWT middleware
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_subscriber(token: str = Depends(oauth2_scheme)):
    # Validates JWT, checks subscription tier, returns subscriber context
    ...
```

## Rate limiting (per subscriber tier)
```python
# Tier limits: Standard=100/min, Pro=1000/min, Enterprise=unlimited
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_subscriber_id)

@app.post("/api/v1/market-risk/monte_carlo_var")
@limiter.limit("100/minute")
async def compute_var(request: VaRRequest, subscriber=Depends(get_current_subscriber)):
    ...
```

## orjson serialisation
```python
# Always use orjson for numpy array serialisation
import orjson
import numpy as np

def numpy_serialiser(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.floating):
        return float(obj)
    raise TypeError

response_bytes = orjson.dumps(result, default=numpy_serialiser)
```

## Dependencies
fastapi >= 0.111 · pydantic >= 2.0 · orjson >= 3.9
python-jose >= 3.3 · slowapi >= 0.1 · uvicorn >= 0.29

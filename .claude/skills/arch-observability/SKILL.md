---
name: pyvar-arch-observability
description: >
  Activate when working on pyvar's observability or security layer:
  Prometheus metrics, Grafana dashboards, Sentry error tracking, Bandit
  static analysis, input validation hardening, or security scanning of
  financial computation code.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [prometheus, grafana, sentry, bandit, observability, monitoring,
       security, metrics, tracing, alerting, input-validation]
---

# pyvar — Architecture: Observability & Security

## Stack
| Component | Role |
|---|---|
| **Prometheus** | Metrics scraping: latency, throughput, error rate |
| **Grafana** | Dashboards: per-domain compute time, queue depth |
| **Sentry** | Error tracking: exception capture with subscriber context |
| **Bandit** | Static security analysis: mandatory CI gate |
| **Pydantic** | Input validation: all API inputs schema-validated |

## Prometheus — FastAPI instrumentation
```python
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Histogram, Counter, Gauge

# Standard metrics
COMPUTE_LATENCY = Histogram(
    "pyvar_compute_duration_seconds",
    "Computation latency by domain and function",
    labelnames=["domain", "function", "tier"]
)
COMPUTE_ERRORS = Counter(
    "pyvar_compute_errors_total",
    "Failed computations by domain",
    labelnames=["domain", "function", "error_type"]
)
QUEUE_DEPTH = Gauge(
    "pyvar_celery_queue_depth",
    "Celery queue depth by domain",
    labelnames=["domain"]
)

# Decorator for all compute functions
def track_metrics(domain: str, function: str):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            with COMPUTE_LATENCY.labels(domain, function, "standard").time():
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    COMPUTE_ERRORS.labels(domain, function,
                                          type(e).__name__).inc()
                    raise
        return wrapper
    return decorator
```

## Sentry — Error capture with context
```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

sentry_sdk.init(
    dsn="https://<key>@sentry.io/<project>",
    integrations=[FastApiIntegration(), CeleryIntegration()],
    traces_sample_rate=0.1,
    environment="production",
)

# Capture with subscriber context
def capture_compute_error(exc: Exception, subscriber_id: str,
                           domain: str, function: str):
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("domain", domain)
        scope.set_tag("function", function)
        scope.set_user({"id": subscriber_id})
        sentry_sdk.capture_exception(exc)
```

## Bandit — Mandatory CI gate
```bash
# .github/workflows/security.yml (or equivalent CI config)
# Run before every merge to main:

bandit -r pyvar/ \
  --severity-level medium \
  --confidence-level medium \
  --exclude pyvar/tests/ \
  -f json -o bandit-report.json

# Block merge if any HIGH severity findings
python -c "
import json, sys
report = json.load(open('bandit-report.json'))
highs = [r for r in report['results'] if r['issue_severity']=='HIGH']
if highs:
    print(f'BLOCKED: {len(highs)} high-severity findings')
    sys.exit(1)
"
```

## Input validation — security hardening
```python
from pydantic import BaseModel, Field, validator
import numpy as np

class MarketRiskRequest(BaseModel):
    returns: list[float] = Field(..., min_items=10, max_items=100_000)
    confidence: float    = Field(0.99, ge=0.50, le=0.9999)
    horizon: int         = Field(1, ge=1, le=500)

    @validator("returns")
    def no_extreme_values(cls, v):
        arr = np.array(v)
        if np.any(np.abs(arr) > 10.0):      # > 1000% return = data error
            raise ValueError("Returns contain extreme outliers (|r| > 10)")
        if np.any(np.isnan(arr)):
            raise ValueError("NaN values not permitted in returns")
        if np.any(np.isinf(arr)):
            raise ValueError("Inf values not permitted in returns")
        return v

    @validator("returns")
    def min_variance(cls, v):
        if np.std(v) < 1e-10:
            raise ValueError("Zero-variance returns series rejected")
        return v
```

## Grafana dashboard definitions (key panels)
```
Panel 1: Compute latency p50/p95/p99 by domain (line chart)
Panel 2: Error rate by domain (bar chart, threshold alert at 1%)
Panel 3: Celery queue depth by domain (gauge, alert at 1000)
Panel 4: Active subscribers (counter)
Panel 5: Redis cache hit rate (gauge, alert below 70%)
Panel 6: S3 storage growth (time series)
```

## Security checklist for every new function
```
☐ Input validated via Pydantic before computation
☐ No raw SQL — SQLAlchemy ORM only
☐ No subprocess calls unless sandboxed
☐ Bandit scan passes with zero HIGH findings
☐ Division by zero / log(0) guarded explicitly
☐ Result size bounded (max 100MB per response)
☐ Subscriber-scoped cache keys (no cross-tenant leakage)
```

## Dependencies
prometheus-client >= 0.19 · prometheus-fastapi-instrumentator >= 0.9
sentry-sdk >= 1.40 · bandit >= 1.7 · pydantic >= 2.0

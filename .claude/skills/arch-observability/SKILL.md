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
| **Bandit** | Static security analysis: runs in CI, visible but not yet merge-blocking (`--exit-zero`) |
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

## Sentry — DSN resolved by the app itself, NOT via ECS-native `secrets={}`
`observability/setup.py::_resolve_sentry_dsn()` deliberately does not rely on
ECS's native task-definition `secrets={}` injection for `SENTRY_DSN`, unlike
`JWT_SECRET`/`DB_*` (which do use it — see `api_stack.py`). ECS-native secret
injection has no "optional" mode: if a listed secret ever becomes unreadable
(deleted, rotated, IAM policy changed), **every** new Fargate task launch
fails outright at secret resolution — with `deployment_circuit_breaker`
(rollback=True) + `min_healthy_percent=100` for HA, that would block every
future prod deploy over what is purely an observability nice-to-have.
Instead, Sentry is fetched at application startup, where a failure degrades
gracefully instead of failing ECS task launch:
```python
def _resolve_sentry_dsn() -> str:
    # Workers get SENTRY_DSN pre-populated into secrets.env by
    # scripts/fetch-config.sh before the process starts, so cfg.sentry_dsn
    # is already set there and this returns immediately.
    if cfg.sentry_dsn:
        return cfg.sentry_dsn
    # Only attempt the Secrets Manager fetch when actually running in a real
    # ECS task — gated on cfg.ecs_container_metadata_uri_v4 (AWS injects this
    # automatically into every real Fargate/EC2 task), NOT on an app_env
    # string. CI's test job runs with APP_ENV=test (not "development"), so a
    # name-based check would let a real AWS call slip into test runs,
    # violating CLAUDE.md's "never use real AWS services in tests" rule.
    if not cfg.ecs_container_metadata_uri_v4:
        return ""
    try:
        import boto3
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=f"pyvar/{cfg.app_env}/sentry-dsn")
        return str(response.get("SecretString") or "")
    except Exception:
        return ""  # Sentry must never become a hard startup dependency
```
`setup_sentry()` treats the literal string `"None"` the same as "not
configured" — a known quirk of `aws secretsmanager get-secret-value --query
SecretString --output text` when a secret was created as `SecretBinary`
instead of `SecretString` (an easy mistake for a secret made outside CDK).

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

sentry_sdk.init(
    dsn=dsn,
    environment=cfg.app_env,
    integrations=[FastApiIntegration(transaction_style="endpoint"),
                  CeleryIntegration(monitor_beat_tasks=True), SqlalchemyIntegration()],
    traces_sample_rate=0.1 if cfg.app_env == "production" else 1.0,
    send_default_pii=False,
)
```

## Bandit — CI-visible, NOT currently a merge-blocking gate
`.github/workflows/ci.yml`'s actual invocation:
```bash
bandit -r . -ll -x tests/ --exit-zero
# -ll = report MEDIUM and HIGH severity only
# --exit-zero: the build NEVER fails on Bandit findings today — this is a
# deliberate interim state ("Remove --exit-zero once all MEDIUM findings
# are resolved" per the workflow's own comment), not an oversight. Do not
# describe this as a "mandatory gate that blocks merge on HIGH severity" —
# it currently only surfaces findings in CI logs/artifacts. `pyproject.toml`'s
# `[tool.bandit]` also carries `skips = ["B101", "B311", "B403"]` (assert
# usage, non-cryptographic random, subprocess import) — check that list
# before treating a given finding as unaddressed.
```
Tightening this to an actual `exit 1` on HIGH findings (as the pattern below
shows) is a real, tracked follow-up — not yet shipped:
```python
# Intended end state, not current CI behavior:
import json, sys
report = json.load(open("bandit-report.json"))
highs = [r for r in report["results"] if r["issue_severity"] == "HIGH"]
if highs:
    print(f"BLOCKED: {len(highs)} high-severity findings")
    sys.exit(1)
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
No Grafana provisioning (dashboards-as-code, Terraform, or CDK) exists in
this repo — `observability/queries.sql` frames itself as "the basis for a
Grafana/QuickSight panel", run manually or from a scheduled job. Treat the
panel list below as a recommended layout to build against Prometheus/
CloudWatch, not as something already deployed:
```
Panel 1: Compute latency p50/p95/p99 by domain (line chart)
Panel 2: Error rate by domain (bar chart, threshold alert at 1%)
Panel 3: Celery queue depth by domain (gauge, alert at 1000)
Panel 4: Active subscribers (counter)
Panel 5: Redis cache hit rate (gauge, alert below 70%)
Panel 6: S3 storage growth (time series)
```

## Alerting fan-out — SNS topic, no subscribers created by CDK
`pyvar-cdk/stacks/alerts_stack.py` creates one SNS topic
(`pyvar-{env}-alerts`) that every CloudWatch alarm (API latency p95, API 5xx,
worker errors, SES bounce/complaint suppression) and the monthly cost budget
publish to — but CDK provisions the topic only, deliberately with **no
subscriptions**, so no per-person email/Slack/PagerDuty endpoint lives in
source control. Subscribers are added manually post-deploy:
```bash
aws sns subscribe --topic-arn <AlertsTopicArn> --protocol email \
  --notification-endpoint ops@example.com --region eu-west-1
```
### Production lesson: `sns subscribe` succeeding is not the same as alerts working
The CLI call above returns success immediately regardless of whether anyone
will ever see an alert — an email-protocol SNS subscription sits in
`PendingConfirmation` until the recipient clicks the confirmation link in the
email SNS sends them. Until that confirmation happens, the subscribe call's
apparent success is a false signal that alerting is live: alarms will fire
into the topic and be silently dropped for that endpoint. Confirm the
subscription (`aws sns list-subscriptions-by-topic --topic-arn ...` shows
`SubscriptionArn: "PendingConfirmation"` vs. a real ARN) as a mandatory step
after every new subscriber is added, not just after the initial launch.

## Security checklist for every new function
```
☐ Input validated via Pydantic before computation
☐ No raw SQL — SQLAlchemy ORM only
☐ No subprocess calls unless sandboxed
☐ Bandit scan reviewed for new HIGH findings (CI reports but does not yet block on them — see Bandit section)
☐ Division by zero / log(0) guarded explicitly
☐ Result size bounded (max 100MB per response)
☐ Subscriber-scoped cache keys (no cross-tenant leakage)
```

## Dependencies
prometheus-client >= 0.19 · prometheus-fastapi-instrumentator >= 0.9
sentry-sdk >= 1.40 · bandit >= 1.7 · pydantic >= 2.0

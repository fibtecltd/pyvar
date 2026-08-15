---
name: pyvar-arch-storage
description: >
  Activate when working on pyvar's storage layer: Redis result cache,
  PostgreSQL schema design, SQLAlchemy ORM models, PyArrow + S3/MinIO
  object storage, Parquet scenario files, or result TTL management.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [redis, postgresql, sqlalchemy, s3, minio, parquet, arrow-ipc,
       storage, cache, orm, object-storage, result-store]
---

# pyvar — Architecture: Results & Storage

## Stack
| Store | Technology | Purpose |
|---|---|---|
| **Hot cache** | Redis | Intraday VaR, live marks, task results (TTL 1h) |
| **Relational** | PostgreSQL + SQLAlchemy | Audit trail, ECL, backtest history |
| **Object store** | PyArrow + S3 / MinIO | Scenario files, large result matrices |

## Redis — Result cache (api/routes/caching.py, the real pattern)
```python
# NOT redis.Redis(db=1) — a single ElastiCache Serverless cluster serves the
# Celery broker/backend, the result cache, AND the rate limiter, distinguished
# only by key prefix ("pyvar:{domain}:..." for cache, "pyvar-ratelimit:..."
# for slowapi) — not by Redis db number. The connection string comes from
# storage/redis_client.py::redis_url(), shared by both callers (see below).
import redis.asyncio as aioredis
import hashlib, json

async def _cache_get(domain: str, params: dict) -> dict | None:
    client = aioredis.from_url(redis_url(), decode_responses=True)
    try:
        raw = await client.get(_cache_key(domain, params))
    except Exception:
        return None  # fail open — a Redis outage must never break a request
    return json.loads(raw) if raw is not None else None

def _cache_key(domain: str, params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return f"pyvar:{domain}:{hashlib.sha256(canonical.encode()).hexdigest()}"
```
### Production lesson: the ElastiCache SSL query param bug
`CELERY_RESULT_BACKEND`/cache URLs on AWS are
`rediss://<endpoint>:6379/0?ssl_cert_reqs=CERT_NONE` (Kombu's convention).
`redis.asyncio.from_url()` does NOT coerce `ssl_cert_reqs` at all, and —
despite kwargs normally overriding URL values — querystring values win over
explicit kwargs for `from_url()`, so passing the real enum as a kwarg is
silently clobbered by the uppercase string, raising `RedisError("Invalid SSL
Certificate Requirements Flag: CERT_NONE")` (`SSLConnection`'s `CERT_REQS`
dict is lowercase-only). `storage/redis_client.py::redis_url()` rewrites the
query param itself (lowercases + strips the `CERT_` prefix) before handing
the URL to any caller — both the async cache client here and the plain sync
`redis` client `api/middleware/rate_limit.py`'s `limits.RedisStorage` builds
hit the identical bug via their own internal `redis.from_url()` calls, which
is why this fix lives in one shared helper rather than being duplicated.

## SQLAlchemy — ORM models (storage/models.py, the real schema)
```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Integer, DateTime, Index

class Base(DeclarativeBase): pass

class VaRJob(Base):
    """Regulatory AUDIT LOG (CLAUDE.md §3.3) — rows are never deleted.
    Created `pending` synchronously in api/routes/var.py BEFORE Celery
    dispatch (fail-loud: if this INSERT fails, the request 503s and the job
    is never queued); updated to its terminal state by tasks/var_task.py
    on completion (best-effort — by then the HTTP request has already
    returned 202, so there's no caller left to fail loud to)."""
    __tablename__ = "var_jobs"
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), default="free")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    var_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    __table_args__ = (Index("ix_var_jobs_user_created", "user_id", "created_at"),)

class ApiUsage(Base):
    """Operational telemetry, NOT the audit log — one row per compute
    request, no client identity/order data, safe to prune on a retention
    schedule (unlike VaRJob). BigInteger identity PK, not UUID: append-heavy
    telemetry with a monotonic key avoids the index fragmentation random
    UUIDv4 PKs cause on high-volume inserts."""
    __tablename__ = "api_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
```

## PostgreSQL — async pattern (storage/session.py — SQLAlchemy async engine, not raw asyncpg)
```python
# The app uses SQLAlchemy's async engine over asyncpg (create_async_engine),
# not a bare asyncpg.Pool + hand-written SQL. Two SEPARATE engines exist,
# for a specific reason: asyncpg connections are bound to the event loop
# that opened them, so driving the async sessionmaker from the (sync,
# prefork) Celery worker via asyncio.run() per task would open a fresh event
# loop every call and defeat connection pooling entirely.
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# FastAPI request path — small pool (writers are the fire-and-forget
# usage-tracking middleware + the var_jobs submission INSERT)
engine = create_async_engine(cfg.postgres_dsn, pool_size=5, max_overflow=5,
                              pool_pre_ping=True, pool_recycle=1800)

# Celery worker — its OWN sync engine over psycopg2 (same driver Alembic
# already uses offline), never sharing the async engine above
sync_engine = create_engine(
    cfg.postgres_dsn.replace("postgresql+asyncpg://", "postgresql+psycopg2://"),
    pool_size=2, max_overflow=2, pool_pre_ping=True, pool_recycle=1800,
)
```
On AWS, `cfg.postgres_dsn` is assembled from five individually-injected
Secrets Manager fields (`DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/
`DB_PASSWORD`) via a `model_validator` in `config.py` — ECS's `secrets={}`
can inject separate string fields but cannot compose a multi-field DSN from
one secret key, so the app assembles it itself, URL-encoding user/password.

## S3 — Parquet result offload (storage/s3.py, the real pattern)
```python
# Plain boto3, not pyarrow.fs.S3FileSystem — and no hardcoded credentials.
# Real AWS relies on boto3's default credential chain (ECS task role);
# explicit access/secret keys are passed ONLY when cfg.s3_endpoint_url is
# set, i.e. pointing at a local MinIO container for dev, which has no IAM
# role to assume.
import boto3, io
import pyarrow as pa
import pyarrow.parquet as pq

def get_s3_client():
    kwargs = {"region_name": cfg.s3_region}
    if cfg.s3_endpoint_url:  # MinIO only
        kwargs.update(endpoint_url=cfg.s3_endpoint_url,
                       aws_access_key_id=cfg.s3_access_key,
                       aws_secret_access_key=cfg.s3_secret_key)
    return boto3.client("s3", **kwargs)

def write_result_to_s3(result: dict, task_id: str) -> str:
    s3_key = f"results/{task_id[:8]}/{task_id}.parquet"
    table = pa.table({...}, schema=RESULT_SCHEMA)  # see arch-data-ingestion
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    get_s3_client().put_object(Bucket=cfg.s3_bucket, Key=s3_key, Body=buffer.read())
    return s3_key
```

## Storage routing — driven by simulation count, not a generic size threshold
```python
# tasks/var_task.py — NOT a generic "size_bytes < X" branch across Redis/PG/S3.
# Above cfg.s3_result_offload_threshold simulations (#130, default = the
# free-tier simulation cap: every free-tier request always stays inline),
# the full result (incl. the multi-MB loss_dist array) is written to S3 as
# Parquet and loss_dist is stripped from what goes back through Celery's
# Redis result backend. At/below the threshold, behavior is unchanged:
# loss_dist inline, no S3 write. hydrate_presigned_url() attaches a FRESH
# presigned URL at every point a result reaches a client (GET /var/result
# and the cache-hit path) rather than baking one in once at compute time,
# so it never goes stale regardless of how long after completion it's
# fetched. Redis (via Celery's result backend) and PostgreSQL (VaRJob,
# scalar fields only) are always both written for a completed job — this is
# not an either/or across the three stores; only whether the FULL result
# also lands in S3 is threshold-gated.
if result["n_simulations"] > cfg.s3_result_offload_threshold:
    result["s3_key"] = write_result_to_s3(result, task_id)
    result["loss_dist"] = []
```

## Dependencies
redis >= 5.0 · sqlalchemy >= 2.0 · asyncpg >= 0.29
pyarrow >= 14.0 · boto3 >= 1.34 (S3) · orjson >= 3.9

## Production lessons (P9 launch)

### Aurora engine version pins go stale when AWS deprecates them
`pyvar-cdk/stacks/data_stack.py`'s `DatabaseCluster` originally pinned
`AuroraPostgresEngineVersion.VER_16_6`. AWS deregistered plain 16.6 in
eu-west-1 (only a `16.6-limitless` variant remained, a different engine mode
this stack doesn't use) — the fix was moving to `VER_16_13`, the newest
plain 16.x release available both in eu-west-1 and in the installed CDK
version's enum. A specific point-version pin is not "set once and forget" —
it needs periodic revalidation against what AWS actually still offers in the
target region, independent of any code change on the pyvar side.

### DB-migration-before-the-app-exists is a real first-bootstrap trap
`pyvar-cdk/stacks/pipeline_stack.py`'s `_migration_step` runs as a `pre` step
of each stage — BEFORE that stage's `ApiStack` (and its ECS task definition)
deploys — and invokes `aws ecs run-task --task-definition
pyvar-{env}-migrate` by FAMILY NAME so it always picks up whatever revision
`ApiStack` most recently pushed. This is the *correct* steady-state ordering
(migrate the schema before rolling out app code that expects the new schema)
— but on a stage's very first-ever deploy, no `pyvar-{env}-migrate` task
definition has ever been registered yet, so `run-task` fails outright
("TaskDefinition not found") before `ApiStack` has had a chance to create
it. Every subsequent run is fine, because it finds the task definition left
behind by the prior deploy. When bootstrapping a brand-new environment,
expect this step to need a one-off manual pass (deploy the stack containing
the task definition once, unblocked from the migration gate, before letting
the pipeline's normal ordering take over) rather than assuming the pipeline
is broken.

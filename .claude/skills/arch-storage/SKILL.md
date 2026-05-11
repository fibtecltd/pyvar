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

## Redis — Result cache
```python
import redis
import orjson

r = redis.Redis(host="localhost", port=6379, db=1)

def cache_result(task_id: str, result: dict, ttl_seconds: int = 3600):
    r.setex(task_id, ttl_seconds, orjson.dumps(result))

def get_cached(task_id: str) -> dict | None:
    raw = r.get(task_id)
    return orjson.loads(raw) if raw else None

# Subscriber-scoped cache key pattern
def cache_key(subscriber_id: str, domain: str, fn: str, params_hash: str) -> str:
    return f"pyvar:{subscriber_id}:{domain}:{fn}:{params_hash}"
```

## SQLAlchemy — ORM models
```python
from sqlalchemy import Column, String, Float, DateTime, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class ComputationResult(Base):
    __tablename__ = "computation_results"
    id            = Column(String, primary_key=True)   # task_id
    subscriber_id = Column(String, nullable=False)
    domain        = Column(String, nullable=False)     # "market_risk"
    function      = Column(String, nullable=False)     # "historical_var"
    params        = Column(JSON)
    result        = Column(JSON)
    computed_at   = Column(DateTime)
    duration_ms   = Column(Float)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id            = Column(String, primary_key=True)
    subscriber_id = Column(String, nullable=False)
    action        = Column(String)                     # "compute" | "read"
    resource      = Column(String)
    timestamp     = Column(DateTime)
    ip_address    = Column(String)
```

## PostgreSQL — async pattern (asyncpg)
```python
import asyncpg

async def save_var_result(pool: asyncpg.Pool, task_id: str,
                           subscriber_id: str, var: float):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO computation_results
                (id, subscriber_id, domain, function, result, computed_at)
            VALUES ($1, $2, 'market_risk', 'var', $3::jsonb, NOW())
            ON CONFLICT (id) DO NOTHING
        """, task_id, subscriber_id, {"var": var})
```

## S3 / MinIO — Scenario file storage
```python
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.fs as pafs

# Write large scenario matrix to S3-compatible store
def write_scenario(scenarios: pa.Table, path: str,
                    endpoint: str = "http://minio:9000"):
    fs = pafs.S3FileSystem(
        endpoint_override=endpoint,
        access_key="pyvar_user",
        secret_key="...",
        scheme="http"
    )
    pq.write_table(scenarios, path, filesystem=fs, compression="snappy")

def read_scenario(path: str, endpoint: str = "http://minio:9000") -> pa.Table:
    fs = pafs.S3FileSystem(endpoint_override=endpoint,
                            access_key="pyvar_user", secret_key="...")
    return pq.read_table(path, filesystem=fs)
```

## Storage routing logic
```python
# Choose store based on result size and access pattern
def store_result(task_id: str, result: dict, size_bytes: int):
    if size_bytes < 100_000:           # < 100 KB → Redis cache
        cache_result(task_id, result)
    elif size_bytes < 10_000_000:      # < 10 MB → PostgreSQL JSONB
        asyncio.run(save_to_pg(task_id, result))
    else:                              # > 10 MB → S3/MinIO Parquet
        write_scenario(result_to_arrow(result), f"results/{task_id}.parquet")
```

## Dependencies
redis >= 5.0 · sqlalchemy >= 2.0 · asyncpg >= 0.29
pyarrow >= 14.0 · boto3 >= 1.34 (S3) · orjson >= 3.9

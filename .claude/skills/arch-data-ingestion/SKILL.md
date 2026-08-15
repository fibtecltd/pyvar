---
name: pyvar-arch-data-ingestion
description: >
  Activate when working on pyvar's data ingestion layer: Polars lazy
  scanning, filter pushdown, Parquet I/O, Arrow IPC, schema validation,
  or converting subscriber market data into pyvar-ready formats.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [polars, pyarrow, parquet, arrow-ipc, data-ingestion,
       lazy-scan, filter-pushdown, schema, etl]
---

# pyvar — Architecture: Data Ingestion

## Stack
| Component | Role |
|---|---|
| **Polars** | Lazy DataFrame engine, filter pushdown, multi-threaded |
| **PyArrow** | Columnar memory format, Parquet I/O, Arrow IPC |
| **Schema registry** | Pydantic-validated field types per domain |

## Polars lazy scan pattern (ingestion/loader.py — the real signature)
```python
import polars as pl
import numpy as np

# Real function returns a NumPy array (not a DataFrame) — the engine layer
# (engine/) knows nothing about Polars/PyArrow, keeping layers separated.
# Column is instrument_id, not asset_id; no streaming=True in the real code
# (fixture/result files are small enough that the default execution engine
# is sufficient — streaming is worth adding if/when input files grow large
# enough to matter, but isn't exercised today).
def load_returns(parquet_path: str, instrument_id: str,
                  start_date=None, end_date=None,
                  return_col: str = "log_return", date_col: str = "date") -> np.ndarray:
    query = pl.scan_parquet(parquet_path).filter(pl.col("instrument_id") == instrument_id)
    if start_date is not None:
        query = query.filter(pl.col(date_col) >= start_date)
    if end_date is not None:
        query = query.filter(pl.col(date_col) <= end_date)
    df = query.select([date_col, return_col]).sort(date_col).collect()
    if df.is_empty():
        raise ValueError(f"No returns found for instrument '{instrument_id}'")
    return df[return_col].to_numpy(allow_copy=False)  # zero-copy via Arrow
```

## PyArrow Parquet I/O (storage/s3.py — the real result schema)
```python
import pyarrow as pa
import pyarrow.parquet as pq

# The actual VaR result schema (storage/s3.py, ingestion/loader.py's
# write_result_parquet) — not a generic "date/asset_id/var_99" shape:
RESULT_SCHEMA = pa.schema([
    pa.field("task_id", pa.string()),
    pa.field("var_pct", pa.float64()),
    pa.field("var_abs", pa.float64()),
    pa.field("cvar_pct", pa.float64()),
    pa.field("cvar_abs", pa.float64()),
    pa.field("mu", pa.float64()),
    pa.field("sigma", pa.float64()),
    pa.field("n_simulations", pa.int64()),
    pa.field("confidence_level", pa.float64()),
    pa.field("horizon_days", pa.int32()),
    pa.field("loss_dist", pa.list_(pa.float64())),  # full sorted loss distribution
])

def write_results(table: pa.Table, path: str) -> None:
    pq.write_table(table, path, compression="snappy", row_group_size=1024)
```

## Arrow IPC for inter-process transfer — not currently used
No file in this codebase imports `pyarrow.ipc` — Celery tasks are dispatched
with plain JSON payloads (`VaRRequest.model_dump()`, see `tasks/var_task.py`
and arch-compute's Celery section), not Arrow IPC buffers, and the only
Arrow round-trip that actually exists is Parquet, not the streaming IPC
format. Treat this as a documented option for a future large-payload
worker-to-worker transfer, not a pattern this codebase exercises today:
```python
import pyarrow as pa
import pyarrow.ipc as ipc

def serialise_for_worker(df: pl.DataFrame) -> bytes:
    buf = pa.BufferOutputStream()
    writer = ipc.new_stream(buf, df.to_arrow().schema)
    writer.write_table(df.to_arrow())
    writer.close()
    return buf.getvalue().to_pybytes()
```

## Schema validation for subscriber data
```python
# Each domain defines expected input schema
MARKET_RISK_SCHEMA = {
    "returns":     pl.Float64,
    "date":        pl.Date,
    "asset_id":    pl.Utf8,
    "portfolio_id":pl.Utf8,
}

def validate_schema(df: pl.DataFrame, expected: dict) -> bool:
    for col, dtype in expected.items():
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")
        if df[col].dtype != dtype:
            raise TypeError(f"{col}: expected {dtype}, got {df[col].dtype}")
    return True
```

## Dependencies
polars >= 0.19 · pyarrow >= 14.0 · pandas >= 2.0 (for QuantLib bridge)

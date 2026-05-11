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

## Polars lazy scan pattern
```python
import polars as pl

# Always use lazy API for large datasets
def load_returns(path: str, start_date: str, end_date: str) -> pl.DataFrame:
    return (
        pl.scan_parquet(path)                        # lazy — no data read yet
        .filter(pl.col("date").is_between(start_date, end_date))
        .filter(pl.col("return").is_not_nan())
        .select(["date", "asset_id", "return"])
        .collect(streaming=True)                     # execute with streaming
    )
```

## PyArrow Parquet I/O
```python
import pyarrow as pa
import pyarrow.parquet as pq

# Write results to Parquet with schema enforcement
RESULT_SCHEMA = pa.schema([
    pa.field("date", pa.date32()),
    pa.field("asset_id", pa.string()),
    pa.field("var_99", pa.float64()),
    pa.field("es_97_5", pa.float64()),
])

def write_results(df: pl.DataFrame, path: str):
    table = df.to_arrow().cast(RESULT_SCHEMA)
    pq.write_table(table, path, compression="snappy")
```

## Arrow IPC for inter-process transfer
```python
import pyarrow as pa
import pyarrow.ipc as ipc

# Efficient zero-copy transfer between Celery workers
def serialise_for_worker(df: pl.DataFrame) -> bytes:
    buf = pa.BufferOutputStream()
    writer = ipc.new_stream(buf, df.to_arrow().schema)
    writer.write_table(df.to_arrow())
    writer.close()
    return buf.getvalue().to_pybytes()

def deserialise_from_worker(data: bytes) -> pl.DataFrame:
    reader = ipc.open_stream(pa.BufferReader(data))
    return pl.from_arrow(reader.read_all())
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

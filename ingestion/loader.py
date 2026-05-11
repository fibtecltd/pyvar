"""
ingestion/loader.py — Polars lazy scan + PyArrow Parquet I/O

Reasoning:
- Polars lazy API (scan_parquet) defers all computation until .collect().
  The query optimiser pushes date filters down to the Parquet reader,
  so only the required row groups are decoded — critical for multi-year files.
- PyArrow is used for writing results back to Parquet.
  pa.Table.from_pydict + pq.write_table gives fine-grained control over
  schema, compression, and partitioning without materialising intermediate objects.
- The loader returns a plain NumPy array to the engine layer — the engine
  knows nothing about Polars or PyArrow, keeping layers cleanly separated.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq


# ── Load returns from Parquet ─────────────────────────────────────────────────

def load_returns(
    parquet_path: str | Path,
    instrument_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    return_col: str = "log_return",
    date_col: str = "date",
) -> np.ndarray:
    """
    Lazily scan a Parquet file, filter by instrument and date range,
    and return the returns column as a NumPy float64 array.

    The Polars lazy API pushes the filter predicates into the Parquet
    reader — only matching row groups are decoded from disk.

    Expected Parquet schema:
        date:          Date
        instrument_id: Utf8
        log_return:    Float64
        close_price:   Float64  (optional)
    """
    query = (
        pl.scan_parquet(parquet_path)
        .filter(pl.col("instrument_id") == instrument_id)
    )

    if start_date is not None:
        query = query.filter(pl.col(date_col) >= start_date)
    if end_date is not None:
        query = query.filter(pl.col(date_col) <= end_date)

    df = (
        query
        .select([date_col, return_col])
        .sort(date_col)
        .collect()
    )

    if df.is_empty():
        raise ValueError(
            f"No returns found for instrument '{instrument_id}' "
            f"in [{start_date}, {end_date}]."
        )

    return df[return_col].to_numpy(allow_copy=False)   # zero-copy via Arrow


def load_multi_instrument(
    parquet_path: str | Path,
    instrument_ids: list[str],
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    """
    Load returns for multiple instruments in a single scan.
    Returns a Polars DataFrame with columns: [date, instrument_id, log_return].
    Useful for portfolio-level aggregation before passing to the engine.
    """
    query = (
        pl.scan_parquet(parquet_path)
        .filter(pl.col("instrument_id").is_in(instrument_ids))
    )

    if start_date is not None:
        query = query.filter(pl.col("date") >= start_date)
    if end_date is not None:
        query = query.filter(pl.col("date") <= end_date)

    return query.sort(["date", "instrument_id"]).collect()


# ── Write results to Parquet (PyArrow) ────────────────────────────────────────

def write_result_parquet(
    result: dict,
    output_path: str | Path,
    task_id: str,
) -> None:
    """
    Persist a VaR result dict to Parquet using PyArrow.

    Stores the full loss distribution alongside scalar metrics.
    Partitioned by task_id for efficient retrieval.

    PyArrow gives control over:
    - Schema enforcement (prevents silent type coercions)
    - Compression codec (snappy for speed, zstd for size)
    - Row group size (tune for downstream scan patterns)
    """
    schema = pa.schema([
        pa.field("task_id",           pa.string()),
        pa.field("var_pct",           pa.float64()),
        pa.field("var_abs",           pa.float64()),
        pa.field("cvar_pct",          pa.float64()),
        pa.field("cvar_abs",          pa.float64()),
        pa.field("mu",                pa.float64()),
        pa.field("sigma",             pa.float64()),
        pa.field("n_simulations",     pa.int64()),
        pa.field("confidence_level",  pa.float64()),
        pa.field("horizon_days",      pa.int32()),
        pa.field("loss_dist",         pa.list_(pa.float64())),
    ])

    table = pa.table(
        {
            "task_id":          [task_id],
            "var_pct":          [result["var_pct"]],
            "var_abs":          [result["var_abs"]],
            "cvar_pct":         [result["cvar_pct"]],
            "cvar_abs":         [result["cvar_abs"]],
            "mu":               [result["mu"]],
            "sigma":            [result["sigma"]],
            "n_simulations":    [result["n_simulations"]],
            "confidence_level": [result["confidence_level"]],
            "horizon_days":     [result["horizon_days"]],
            "loss_dist":        [result["loss_dist"]],
        },
        schema=schema,
    )

    pq.write_table(
        table,
        output_path,
        compression="snappy",        # fast read/write for hot results
        row_group_size=1024,
    )

"""
ingestion/fixtures.py — Synthetic returns generator for development and testing

Reasoning:
- Avoids dependency on real market data during development.
- Generates realistic GBM (Geometric Brownian Motion) log-returns
  with configurable drift and volatility.
- Also writes a fixture Parquet file that the loader.py tests can use.
- Seeds are fixed for deterministic CI test runs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import date, timedelta


def generate_gbm_returns(
    n_obs: int = 252,
    mu: float = 0.0005,        # ~12.5% annualised drift
    sigma: float = 0.012,      # ~19% annualised volatility (FTSE-like)
    seed: int = 42,
) -> np.ndarray:
    """
    Generate synthetic daily log-returns from a Gaussian distribution.
    N(mu, sigma) is the standard parametric assumption for equity returns.
    """
    rng = np.random.default_rng(seed)
    return rng.normal(loc=mu, scale=sigma, size=n_obs)


def generate_fixture_parquet(
    output_path: str | Path,
    instruments: list[str] | None = None,
    n_obs: int = 504,          # 2 years of trading days
    seed: int = 42,
) -> Path:
    """
    Write a fixture Parquet file with synthetic returns for multiple instruments.
    Used by tests and local development without real market data.

    Schema matches what loader.load_returns() expects:
        date:          Date
        instrument_id: Utf8
        log_return:    Float64
    """
    if instruments is None:
        instruments = ["FTSE100", "SP500", "EUROSTOXX50", "NIKKEI225"]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base_date = date(2023, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(n_obs)]

    rows = []
    for i, inst in enumerate(instruments):
        returns = generate_gbm_returns(
            n_obs=n_obs,
            mu=0.0003 + i * 0.0001,
            sigma=0.010 + i * 0.002,
            seed=seed + i,
        )
        for d, r in zip(dates, returns):
            rows.append({"date": d, "instrument_id": inst, "log_return": float(r)})

    df = pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))

    table = pa.Table.from_pandas(df.to_pandas())
    pq.write_table(table, output_path, compression="snappy")

    return output_path

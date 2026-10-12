"""
tests/test_loader.py — ingestion/loader.py (Polars lazy scan -> NumPy)

Reasoning:
- load_returns had no test, so nothing exercised its Polars -> NumPy hand-off.
  The array it returns is what the engine layer consumes, so pin the contract
  here: float64, 1-D, filtered to one instrument and an optional date range,
  and a clear ValueError (not an empty array) when nothing matches.
- Uses ingestion.fixtures.generate_fixture_parquet (synthetic data, tmp_path),
  per the project rule that tests never touch real market data or real AWS.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from ingestion.fixtures import generate_fixture_parquet
from ingestion.loader import load_multi_instrument, load_returns


@pytest.fixture
def parquet_path(tmp_path):
    return generate_fixture_parquet(tmp_path / "fx.parquet", n_obs=504, seed=42)


def test_load_returns_is_float64_1d_for_one_instrument(parquet_path):
    arr = load_returns(parquet_path, "FTSE100")
    assert isinstance(arr, np.ndarray)
    assert arr.dtype == np.float64
    assert arr.ndim == 1
    assert arr.shape == (504,)


def test_load_returns_applies_date_range(parquet_path):
    full = load_returns(parquet_path, "FTSE100")
    windowed = load_returns(
        parquet_path, "FTSE100", start_date=date(2023, 6, 1), end_date=date(2023, 6, 30)
    )
    assert windowed.shape == (30,)
    assert windowed.shape[0] < full.shape[0]


def test_load_returns_unknown_instrument_raises(parquet_path):
    with pytest.raises(ValueError, match="No returns found for instrument 'NOPE'"):
        load_returns(parquet_path, "NOPE")


def test_load_multi_instrument_returns_requested_instruments_only(parquet_path):
    df = load_multi_instrument(parquet_path, ["FTSE100", "SP500"])
    assert set(df["instrument_id"].unique().to_list()) == {"FTSE100", "SP500"}
    assert df.columns == ["date", "instrument_id", "log_return"]

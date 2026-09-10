"""
ingestion/market_data/schemas.py — canonical Pydantic v2 market data models

Reasoning:
- These are the ONLY shapes engine/, api/, and tasks/ are ever meant to see
  (per MD-4, not yet wired). A provider adapter's job is translating its
  vendor's raw response into these models — vendor field names (e.g. RDP's
  `TR.PriceClose`) must never leak past a providers/*.py file.
- ISIN is the one canonical instrument identifier used internally, per
  docs/plan-market-data-adapter.md §2 — a provider is responsible for
  translating ISIN <-> its own vendor code (e.g. RIC for Refinitiv), not
  the other way around. The 12-character length check mirrors the existing
  ISIN validation in engine/reg_mifid_emir.py (MiFID II/EMIR transaction
  reporting field checks), so the same rule is enforced consistently
  wherever an ISIN enters the system.
- `source` on every series/surface model records which provider produced
  it — required for the audit trail (only pyvar's *computed* outputs may
  reach storage/, but knowing which vendor's data fed a computation still
  matters for reproducibility and any future vendor compliance review).
- Follows the same Pydantic v2 + Annotated[Field] style as schemas/var.py.
"""

from __future__ import annotations

from datetime import date
from itertools import pairwise

from pydantic import BaseModel, Field, field_validator

# ── Instrument identity ──────────────────────────────────────────────────────


class Instrument(BaseModel):
    """A single instrument, identified canonically by ISIN."""

    isin: str = Field(description="ISO 6166 International Securities Identification Number")
    currency: str = Field(description="ISO 4217 currency code, e.g. 'GBP'")

    @field_validator("isin")
    @classmethod
    def isin_must_be_12_chars(cls, v: str) -> str:
        """ISO 6166 ISINs are always exactly 12 characters."""
        if len(v) != 12:
            raise ValueError(f"ISIN '{v}' must be exactly 12 characters, got {len(v)}.")
        return v.upper()

    @field_validator("currency")
    @classmethod
    def currency_must_be_3_chars(cls, v: str) -> str:
        """ISO 4217 currency codes are always exactly 3 characters."""
        if len(v) != 3:
            raise ValueError(f"Currency code '{v}' must be exactly 3 characters, got {len(v)}.")
        return v.upper()


# ── Prices ────────────────────────────────────────────────────────────────────


class PricePoint(BaseModel):
    """A single closing price observation."""

    as_of: date = Field(description="Trading date the close price applies to")
    close: float = Field(gt=0, description="Closing price in the instrument's quote currency")
    currency: str = Field(description="ISO 4217 currency code the price is quoted in")


class PriceSeries(BaseModel):
    """A time series of closing prices for one instrument."""

    instrument: Instrument
    points: list[PricePoint] = Field(description="Price observations, ordered by as_of ascending")
    source: str = Field(description="Provider name that produced this series, e.g. 'refinitiv'")

    @field_validator("points")
    @classmethod
    def points_must_be_ordered(cls, v: list[PricePoint]) -> list[PricePoint]:
        """Enforce ascending as_of order so downstream consumers never need to re-sort."""
        for prev, curr in pairwise(v):
            if curr.as_of < prev.as_of:
                raise ValueError("PriceSeries.points must be ordered by as_of ascending.")
        return v


# ── Yield curves ──────────────────────────────────────────────────────────────


class YieldCurve(BaseModel):
    """A single-currency yield curve snapshot, keyed by tenor label."""

    currency: str = Field(description="ISO 4217 currency code the curve applies to")
    as_of: date = Field(description="Curve snapshot date")
    tenors: dict[str, float] = Field(
        description="Tenor label to rate, e.g. {'1M': 0.0512, '1Y': 0.0498}"
    )
    source: str = Field(description="Provider name that produced this curve")


# ── Volatility surfaces ───────────────────────────────────────────────────────


class VolPoint(BaseModel):
    """A single implied volatility observation at a strike/tenor pair."""

    strike: float = Field(gt=0, description="Strike price")
    tenor: str = Field(description="Tenor label, e.g. '3M'")
    implied_vol: float = Field(gt=0, description="Implied volatility, annualised")


class VolSurface(BaseModel):
    """An implied volatility surface for one instrument."""

    instrument: Instrument
    as_of: date = Field(description="Surface snapshot date")
    points: list[VolPoint] = Field(description="Implied volatility observations")
    source: str = Field(description="Provider name that produced this surface")

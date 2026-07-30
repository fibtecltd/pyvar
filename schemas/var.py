"""
schemas/var.py — Pydantic v2 request/response contracts for the VaR API

Reasoning:
- Pydantic v2 is 5-50x faster than v1 for parsing — important at API boundary.
- Field-level validators enforce domain rules (confidence ∈ (0,1), horizon > 0)
  before the request ever reaches the compute layer.
- model_validator for cross-field rules (n_simulations cap vs. account tier).
- VaRResult uses orjson-compatible types (list[float] not np.ndarray)
  so the response serialiser never hits a type error.
- The JobStatus enum drives the polling loop in the frontend.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from config import get_settings

cfg = get_settings()

# ── Enums ─────────────────────────────────────────────────────────────────────


class JobStatus(str, Enum):
    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"


# ── Request ────────────────────────────────────────────────────────────────────


class VaRRequest(BaseModel):
    """
    Parameters submitted by the user to trigger a Monte Carlo VaR computation.
    All fields have sensible defaults matching Basel III standard parameters.
    """

    portfolio_value: Annotated[float, Field(gt=0, description="Portfolio value in base currency")]
    returns: Annotated[
        list[float],
        Field(min_length=30, max_length=10_000, description="Historical daily log-returns"),
    ]
    confidence_level: Annotated[
        float,
        Field(gt=0.0, lt=1.0, default=0.99, description="VaR confidence level, e.g. 0.99"),
    ] = 0.99
    horizon_days: Annotated[
        int,
        Field(ge=1, le=250, default=1, description="Risk horizon in trading days"),
    ] = 1
    n_simulations: Annotated[
        int,
        Field(
            ge=1_000,
            le=cfg.max_n_simulations,
            default=cfg.default_n_simulations,
            description="Number of Monte Carlo paths",
        ),
    ] = cfg.default_n_simulations
    seed: int | None = Field(default=42, description="Random seed for reproducibility")

    @field_validator("confidence_level")
    @classmethod
    def confidence_must_be_standard(cls, v: float) -> float:
        """Warn if confidence level is outside conventional range."""
        if not (0.90 <= v <= 0.9999):
            raise ValueError(
                f"Confidence level {v} is outside conventional range [0.90, 0.9999]. "
                "Standard values: 0.95 (internal), 0.99 (Basel III), 0.975 (FRTB ES)."
            )
        return v

    @field_validator("returns")
    @classmethod
    def returns_must_be_finite(cls, v: list[float]) -> list[float]:
        """Reject NaN or infinite values in the returns series."""
        import math

        if any(not math.isfinite(r) for r in v):
            raise ValueError("Returns series contains NaN or infinite values.")
        return v


# ── Response ───────────────────────────────────────────────────────────────────


class VaRResult(BaseModel):
    """
    Computed VaR result returned to the client.
    loss_dist is the full sorted loss distribution as a list (orjson serialises this natively) —
    EXCEPT above cfg.s3_result_offload_threshold simulations (#130), where tasks/var_task.py
    writes it to S3 instead and this is an empty list; presigned_url is populated instead
    (freshly generated per request — see storage/s3.py::hydrate_presigned_url).
    """

    var_pct: float = Field(description="VaR as proportion of portfolio value")
    var_abs: float = Field(description="VaR in absolute currency terms")
    cvar_pct: float = Field(description="CVaR (Expected Shortfall) as proportion")
    cvar_abs: float = Field(description="CVaR in absolute currency terms")
    loss_dist: list[float] = Field(description="Full sorted loss distribution (as % of portfolio)")
    mu: float = Field(description="Fitted daily mean return")
    sigma: float = Field(description="Fitted daily volatility")
    n_simulations: int
    confidence_level: float
    horizon_days: int
    s3_key: str | None = Field(
        default=None, description="S3 key for the full result, if offloaded (#130)"
    )
    presigned_url: str | None = Field(
        default=None, description="Presigned URL for loss_dist, if offloaded (#130)"
    )


class JobResponse(BaseModel):
    """Returned immediately on POST /var/compute — client uses task_id to poll."""

    task_id: str
    status: JobStatus = JobStatus.PENDING
    message: str = "Job queued successfully"


class JobResultResponse(BaseModel):
    """Returned on GET /var/result/{task_id}."""

    task_id: str
    status: JobStatus
    result: VaRResult | None = None
    error: str | None = None

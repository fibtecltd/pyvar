"""
api/errors.py — exception handlers shared by every route

Reasoning:
- FastAPI's default RequestValidationError handler echoes the offending
  value back under ``input``. When that value is NaN or Infinity (JSON bodies
  may carry the non-standard tokens ``NaN`` / ``Infinity``, and pydantic also
  parses the strings "nan" / "inf"), serialising the 422 body fails and the
  client sees a 500 instead of the validation error.
- This handler produces the same body as the default one but renders
  non-finite floats as strings, so a bad number is reported as a 422.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _json_safe(value: Any) -> Any:
    """Recursively replace non-finite floats with their string form."""
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422 with the default body shape, safe for non-finite numbers in ``input``."""
    return JSONResponse(
        status_code=422,
        content={"detail": _json_safe(jsonable_encoder(exc.errors()))},
    )

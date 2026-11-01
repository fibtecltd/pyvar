"""plugins/mcp/pyvar_mcp/_generated/__init__.py — GENERATED, do not edit by hand.

All the tools, one module per domain (the same order as portal/functions.json).
Regenerate with: python3 scripts/generate_mcp_tools.py (from the repo root).
"""

from __future__ import annotations

from typing import Any

from . import (
    alm,
    credit_risk,
    derivatives,
    liquidity,
    market_risk,
    operational,
    portfolio,
    regulatory,
)

FUNCTIONS: list[dict[str, Any]] = [
    *alm.FUNCTIONS,
    *credit_risk.FUNCTIONS,
    *derivatives.FUNCTIONS,
    *liquidity.FUNCTIONS,
    *market_risk.FUNCTIONS,
    *operational.FUNCTIONS,
    *portfolio.FUNCTIONS,
    *regulatory.FUNCTIONS,
]

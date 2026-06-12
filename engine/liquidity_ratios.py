"""engine/liquidity_ratios.py — Basel III liquidity ratio family.

Implements the regulatory liquidity ratios and their building blocks:
LCR, NSFR, Available/Required Stable Funding, and the three HQLA asset
classifiers (Level 1, 2A, 2B).

Regulatory references:
  * LCR — Basel III (BCBS 238): ``LCR = HQLA / net 30-day cash outflows`` and
    must be >= 100%. Total net outflows are floored so the inflow offset cannot
    exceed 75% of gross outflows (the "75% cap").
  * NSFR — Basel III (BCBS 295): ``NSFR = ASF / RSF`` and must be >= 100%.
  * HQLA composition caps (BCBS 238 §46-§47): Level 2 assets <= 40% of total
    HQLA; Level 2B assets <= 15% of total HQLA. Level 2A haircut 15%, Level 2B
    haircuts 25%-50%.

These are aggregation / typed-Python wrappers — there is no heavy array math,
so per CLAUDE.md §3.1 guidance no @njit kernels are used here. All ratios are
returned as decimals (1.15 == 115%).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "liquidity_coverage_ratio_lcr",
    "net_stable_funding_ratio_nsfr",
    "available_stable_funding_asf_calc",
    "required_stable_funding_rsf_calc",
    "hqla_level_1_asset_classifier",
    "hqla_level_2a_asset_classifier",
    "hqla_level_2b_asset_classifier",
]

# Basel III LCR inflow cap: recognised inflows may offset at most 75% of
# gross outflows (BCBS 238 §69).
_LCR_INFLOW_CAP = 0.75
# HQLA composition caps (BCBS 238 §46-§47).
_LEVEL2_CAP = 0.40
_LEVEL2B_CAP = 0.15
# Standard supervisory haircuts.
_HAIRCUT_2A = 0.15
_HAIRCUT_2B_MIN = 0.25


def liquidity_coverage_ratio_lcr(
    hqla: float,
    gross_outflows: float,
    gross_inflows: float,
    inflow_cap: float = _LCR_INFLOW_CAP,
) -> dict:  # type: ignore[type-arg]
    """Basel III Liquidity Coverage Ratio.

    ``LCR = HQLA / net 30-day outflows`` where net outflows are gross outflows
    minus *capped* inflows. Recognised inflows are floored at ``inflow_cap`` of
    gross outflows (default 75%), guaranteeing net outflows never fall below
    25% of gross — the BCBS 238 §69 cap.

    Args:
        hqla: Stock of high-quality liquid assets (post-haircut).
        gross_outflows: Total expected 30-day stressed cash outflows.
        gross_inflows: Total expected 30-day contractual cash inflows.
        inflow_cap: Maximum fraction of gross outflows that inflows may offset.

    Returns:
        Dict with ``lcr`` (decimal), ``net_outflows``, ``capped_inflows`` and a
        boolean ``compliant`` flag (LCR >= 1.0).

    Raises:
        ValueError: If any input is negative or ``gross_outflows`` is zero.
    """
    if hqla < 0 or gross_outflows < 0 or gross_inflows < 0:
        raise ValueError("LCR inputs must be non-negative")
    if gross_outflows == 0:
        raise ValueError("gross_outflows must be positive")

    capped_inflows = min(gross_inflows, inflow_cap * gross_outflows)
    net_outflows = gross_outflows - capped_inflows
    # Net outflows floored at (1 - cap) * gross by construction; still guard /0.
    net_outflows = max(net_outflows, (1.0 - inflow_cap) * gross_outflows)
    lcr = hqla / net_outflows
    return {
        "lcr": round(float(lcr), 6),
        "net_outflows": round(float(net_outflows), 2),
        "capped_inflows": round(float(capped_inflows), 2),
        "hqla": round(float(hqla), 2),
        "compliant": bool(lcr >= 1.0),
    }


def available_stable_funding_asf_calc(
    funding_amounts: np.ndarray,
    asf_factors: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Available Stable Funding for the NSFR numerator.

    ASF is the weighted sum of funding sources by their ASF factor. Basel III
    assigns higher factors to more stable funding (e.g. capital and >1y funding
    = 100%, stable retail deposits = 95%, less-stable = 90%, wholesale <1y
    typically 50% or 0%).

    Args:
        funding_amounts: Carrying amounts of each funding source.
        asf_factors: ASF factor for each source, each in [0, 1].

    Returns:
        Dict with ``asf`` (total) and ``components`` (per-source weighted).

    Raises:
        ValueError: If array lengths differ or factors lie outside [0, 1].
    """
    amounts = np.asarray(funding_amounts, dtype=np.float64)
    factors = np.asarray(asf_factors, dtype=np.float64)
    if amounts.shape != factors.shape:
        raise ValueError("funding_amounts and asf_factors must have equal length")
    if np.any(factors < 0.0) or np.any(factors > 1.0):
        raise ValueError("asf_factors must lie in [0, 1]")

    components = amounts * factors
    return {
        "asf": round(float(np.sum(components)), 2),
        "components": [round(float(c), 2) for c in components],
    }


def required_stable_funding_rsf_calc(
    asset_amounts: np.ndarray,
    rsf_factors: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Required Stable Funding for the NSFR denominator.

    RSF is the weighted sum of assets by their RSF factor. More liquid / shorter
    assets attract lower factors (Level 1 HQLA = 5%, Level 2A = 15%, loans = 50-
    85%, illiquid assets = 100%).

    Args:
        asset_amounts: Carrying amounts of each asset / off-balance item.
        rsf_factors: RSF factor for each asset, each in [0, 1].

    Returns:
        Dict with ``rsf`` (total) and ``components`` (per-asset weighted).

    Raises:
        ValueError: If array lengths differ or factors lie outside [0, 1].
    """
    amounts = np.asarray(asset_amounts, dtype=np.float64)
    factors = np.asarray(rsf_factors, dtype=np.float64)
    if amounts.shape != factors.shape:
        raise ValueError("asset_amounts and rsf_factors must have equal length")
    if np.any(factors < 0.0) or np.any(factors > 1.0):
        raise ValueError("rsf_factors must lie in [0, 1]")

    components = amounts * factors
    return {
        "rsf": round(float(np.sum(components)), 2),
        "components": [round(float(c), 2) for c in components],
    }


def net_stable_funding_ratio_nsfr(
    available_stable_funding: float,
    required_stable_funding: float,
) -> dict:  # type: ignore[type-arg]
    """Basel III Net Stable Funding Ratio.

    ``NSFR = ASF / RSF`` and must be >= 100% (BCBS 295). Measures the proportion
    of long-term assets funded by stable funding sources over a one-year horizon.

    Args:
        available_stable_funding: Total ASF (see
            :func:`available_stable_funding_asf_calc`).
        required_stable_funding: Total RSF (see
            :func:`required_stable_funding_rsf_calc`).

    Returns:
        Dict with ``nsfr`` (decimal) and ``compliant`` flag (NSFR >= 1.0).

    Raises:
        ValueError: If inputs are negative or RSF is zero.
    """
    if available_stable_funding < 0 or required_stable_funding < 0:
        raise ValueError("NSFR inputs must be non-negative")
    if required_stable_funding == 0:
        raise ValueError("required_stable_funding must be positive")

    nsfr = available_stable_funding / required_stable_funding
    return {
        "nsfr": round(float(nsfr), 6),
        "asf": round(float(available_stable_funding), 2),
        "rsf": round(float(required_stable_funding), 2),
        "compliant": bool(nsfr >= 1.0),
    }


def hqla_level_1_asset_classifier(
    asset_values: np.ndarray,
    haircuts: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Classify and value Level 1 HQLA.

    Level 1 assets (cash, central-bank reserves, 0%-risk-weight sovereign debt)
    receive a 0% haircut by default and have no composition cap (BCBS 238 §50).

    Args:
        asset_values: Market values of candidate Level 1 assets.
        haircuts: Optional per-asset haircuts in [0, 1]; defaults to all zeros.

    Returns:
        Dict with ``level`` (1), ``post_haircut_value`` (total) and the per-asset
        ``adjusted_values``.

    Raises:
        ValueError: If haircuts are out of range or length-mismatched.
    """
    values = np.asarray(asset_values, dtype=np.float64)
    if haircuts is None:
        hc = np.zeros_like(values)
    else:
        hc = np.asarray(haircuts, dtype=np.float64)
        if hc.shape != values.shape:
            raise ValueError("haircuts must match asset_values length")
        if np.any(hc < 0.0) or np.any(hc > 1.0):
            raise ValueError("haircuts must lie in [0, 1]")

    adjusted = values * (1.0 - hc)
    return {
        "level": 1,
        "post_haircut_value": round(float(np.sum(adjusted)), 2),
        "adjusted_values": [round(float(a), 2) for a in adjusted],
    }


def hqla_level_2a_asset_classifier(
    asset_values: np.ndarray,
    haircut: float = _HAIRCUT_2A,
) -> dict:  # type: ignore[type-arg]
    """Classify and value Level 2A HQLA.

    Level 2A assets (20%-risk-weight sovereigns, certain covered bonds, high-
    grade corporates) carry a minimum 15% haircut (BCBS 238 §52).

    Args:
        asset_values: Market values of candidate Level 2A assets.
        haircut: Supervisory haircut (minimum 15%).

    Returns:
        Dict with ``level`` (``"2A"``), ``post_haircut_value`` and ``haircut``.

    Raises:
        ValueError: If ``haircut`` is below the 15% regulatory minimum.
    """
    if haircut < _HAIRCUT_2A:
        raise ValueError("Level 2A haircut must be at least 15%")
    values = np.asarray(asset_values, dtype=np.float64)
    adjusted = values * (1.0 - haircut)
    return {
        "level": "2A",
        "post_haircut_value": round(float(np.sum(adjusted)), 2),
        "haircut": round(float(haircut), 4),
        "adjusted_values": [round(float(a), 2) for a in adjusted],
    }


def hqla_level_2b_asset_classifier(
    asset_values: np.ndarray,
    haircut: float = _HAIRCUT_2B_MIN,
) -> dict:  # type: ignore[type-arg]
    """Classify and value Level 2B HQLA.

    Level 2B assets (RMBS 25% haircut, lower-grade corporates and qualifying
    equities 50% haircut) carry a minimum 25% haircut (BCBS 238 §54).

    Args:
        asset_values: Market values of candidate Level 2B assets.
        haircut: Supervisory haircut (minimum 25%).

    Returns:
        Dict with ``level`` (``"2B"``), ``post_haircut_value`` and ``haircut``.

    Raises:
        ValueError: If ``haircut`` is below the 25% regulatory minimum.
    """
    if haircut < _HAIRCUT_2B_MIN:
        raise ValueError("Level 2B haircut must be at least 25%")
    values = np.asarray(asset_values, dtype=np.float64)
    adjusted = values * (1.0 - haircut)
    return {
        "level": "2B",
        "post_haircut_value": round(float(np.sum(adjusted)), 2),
        "haircut": round(float(haircut), 4),
        "adjusted_values": [round(float(a), 2) for a in adjusted],
    }

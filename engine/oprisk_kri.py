"""engine/oprisk_kri.py — Key Risk Indicator (KRI) monitoring.

Implements the KRI sub-domain: the KRI library/registry, threshold-breach
detection (green/amber/red), and trend analysis (linear-regression slope with a
direction verdict).

KRI trend analysis uses an ordinary-least-squares slope — light NumPy linear
algebra, no @njit kernel needed (CLAUDE.md §3.1 guidance).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "key_risk_indicator_kri_library",
    "kri_threshold_breach_detection",
    "kri_trend_analysis",
]


def key_risk_indicator_kri_library(
    kri_definitions: list[dict],  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """Validate and index a KRI library.

    Each KRI definition must carry a ``name``, a numeric ``amber_threshold`` and
    ``red_threshold``, and a ``direction`` (``"higher_breach"`` or
    ``"lower_breach"``). Returns a validated registry keyed by name.

    This is a pure validation/indexing pass — it checks required keys and builds
    the keyed registry, with no numeric computation involved.

    Args:
        kri_definitions: List of KRI definition dicts.

    Returns:
        Dict with ``num_kris`` and ``registry`` (name -> definition).

    Raises:
        ValueError: If the list is empty or an entry is malformed.
    """
    if not kri_definitions:
        raise ValueError("kri_definitions must be non-empty")
    registry: dict[str, dict] = {}  # type: ignore[type-arg]
    for kri in kri_definitions:
        for key in ("name", "amber_threshold", "red_threshold", "direction"):
            if key not in kri:
                raise ValueError(f"KRI missing required key: {key}")
        if kri["direction"] not in ("higher_breach", "lower_breach"):
            raise ValueError("direction must be 'higher_breach' or 'lower_breach'")
        registry[kri["name"]] = kri
    return {"num_kris": len(registry), "registry": registry}


def kri_threshold_breach_detection(
    value: float,
    amber_threshold: float,
    red_threshold: float,
    direction: str = "higher_breach",
) -> dict:  # type: ignore[type-arg]
    """Classify a KRI value into a green/amber/red status.

    For ``higher_breach`` KRIs (higher = worse, e.g. failed trades) the value
    crosses amber then red as it rises; for ``lower_breach`` KRIs (lower = worse,
    e.g. staffing level) it crosses as it falls.

    For ``lower_breach`` every inequality above is reversed (red at or below the
    red threshold, amber between red and amber, green above amber).

    Args:
        value: Current KRI observation.
        amber_threshold: Amber boundary.
        red_threshold: Red boundary (more extreme than amber).
        direction: ``"higher_breach"`` or ``"lower_breach"``.

    Returns:
        Dict with ``status`` (``"green"``/``"amber"``/``"red"``) and ``breached``
        (status != green).

    Raises:
        ValueError: If ``direction`` is invalid or thresholds are ordered
            inconsistently with the direction.
    """
    if direction == "higher_breach":
        if red_threshold < amber_threshold:
            raise ValueError("red_threshold must be >= amber_threshold for higher_breach")
        if value >= red_threshold:
            status = "red"
        elif value >= amber_threshold:
            status = "amber"
        else:
            status = "green"
    elif direction == "lower_breach":
        if red_threshold > amber_threshold:
            raise ValueError("red_threshold must be <= amber_threshold for lower_breach")
        if value <= red_threshold:
            status = "red"
        elif value <= amber_threshold:
            status = "amber"
        else:
            status = "green"
    else:
        raise ValueError("direction must be 'higher_breach' or 'lower_breach'")
    return {"status": status, "breached": bool(status != "green")}


def kri_trend_analysis(
    observations: np.ndarray,
    higher_is_worse: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Linear-trend analysis of a KRI time series.

    Fits an OLS slope to the observation series and classifies the trend as
    ``"deteriorating"``, ``"improving"`` or ``"stable"`` based on the slope sign
    and the metric direction.

    "Stable" is a scale-relative rule (``|slope| < 1e-4 * mean(|observations|)``),
    not a fixed absolute tolerance, and the deteriorating/improving call flips
    with ``higher_is_worse``.

    Args:
        observations: Ordered KRI observations (oldest first).
        higher_is_worse: Whether an increasing series is adverse.

    Returns:
        Dict with ``slope``, ``trend`` and ``latest`` (last observation).

    Raises:
        ValueError: If fewer than 2 observations are supplied.
    """
    obs = np.asarray(observations, dtype=np.float64)
    if obs.size < 2:
        raise ValueError("trend analysis requires at least 2 observations")

    x = np.arange(obs.size, dtype=np.float64)
    slope = float(np.polyfit(x, obs, 1)[0])
    # Threshold for "stable" relative to the series scale.
    scale = float(np.mean(np.abs(obs))) or 1.0
    if abs(slope) < 1e-4 * scale:
        trend = "stable"
    else:
        rising = slope > 0
        adverse = rising if higher_is_worse else not rising
        trend = "deteriorating" if adverse else "improving"
    return {
        "slope": round(slope, 8),
        "trend": trend,
        "latest": round(float(obs[-1]), 6),
    }

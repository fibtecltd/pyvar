"""engine/reg_basel_capital.py — Basel III/IV capital, buffers & CRR2.

Implements the Basel III/IV Capital Ratios, ICAAP/SREP/Pillar 2 and CRR2 &
Capital Buffer regulatory sub-domains:
  * Basel III CET1, Tier 1 and Total capital ratios; Leverage ratio.
  * Basel IV output floor (72.5%).
  * ICAAP capital assessment, SREP add-on, Pillar 2A, Pillar 2B stress buffer.
  * Combined buffer, capital conservation buffer, countercyclical buffer.
  * CRR2 large exposure limit.

Regulatory thresholds (CLAUDE.md §4) are hard-coded as named constants and must
not be parameterised away. These are reporting/aggregation functions: pure
typed NumPy/Python wrappers (no @njit needed — no array hot loops). Capital
ratios are decimals (0.15 == 15%); RWA and exposures are currency amounts.

References:
  * Basel III: A global regulatory framework (BCBS, rev. 2011), §50, §52, §94.
  * CRR2 (Regulation (EU) 2019/876), Art. 92, Art. 395 (large exposures).
  * Basel IV output floor: Basel III finalisation (BCBS, Dec 2017), §46.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "basel_iii_cet1_ratio",
    "basel_iii_tier1_ratio",
    "basel_iii_total_capital_ratio",
    "basel_iii_leverage_ratio",
    "basel_iv_output_floor",
    "icaap_capital_assessment",
    "srep_capital_add_on",
    "pillar_2a_capital",
    "pillar_2b_stress_buffer",
    "combined_buffer_requirement",
    "capital_conservation_buffer",
    "countercyclical_capital_buffer",
    "crr2_large_exposure_limit",
]

# ── Basel regulatory minimums (decimal fractions of RWA) ──────────────────────
CET1_MINIMUM: float = 0.045  # 4.5% (Basel III §50)
TIER1_MINIMUM: float = 0.06  # 6.0% (Basel III §50)
TOTAL_CAPITAL_MINIMUM: float = 0.08  # 8.0% (Basel III §50)
LEVERAGE_RATIO_MINIMUM: float = 0.03  # 3.0% (Basel III leverage framework)
CAPITAL_CONSERVATION_BUFFER: float = 0.025  # 2.5% (Basel III §122)
OUTPUT_FLOOR_FACTOR: float = 0.725  # 72.5% (Basel IV finalisation)
LARGE_EXPOSURE_LIMIT: float = 0.25  # 25% of Tier 1 (CRR2 Art. 395)


def basel_iii_cet1_ratio(
    cet1_capital: float,
    risk_weighted_assets: float,
) -> dict:  # type: ignore[type-arg]
    """Basel III Common Equity Tier 1 (CET1) ratio.

    ``CET1 ratio = CET1 capital / RWA``; minimum 4.5% (Basel III §50).

    Args:
        cet1_capital: Common Equity Tier 1 capital (currency).
        risk_weighted_assets: Total risk-weighted assets (currency).

    Returns:
        Dict with ``cet1_ratio`` (decimal), ``minimum``, ``surplus`` (ratio
        above the minimum) and ``compliant``.

    Raises:
        ValueError: If RWA is non-positive.
    """
    if risk_weighted_assets <= 0.0:
        raise ValueError("risk_weighted_assets must be positive")
    ratio = cet1_capital / risk_weighted_assets
    return {
        "cet1_ratio": round(ratio, 8),
        "minimum": CET1_MINIMUM,
        "surplus": round(ratio - CET1_MINIMUM, 8),
        "compliant": bool(ratio >= CET1_MINIMUM),
    }


def basel_iii_tier1_ratio(
    tier1_capital: float,
    risk_weighted_assets: float,
) -> dict:  # type: ignore[type-arg]
    """Basel III Tier 1 capital ratio.

    ``Tier 1 ratio = Tier 1 capital / RWA``; minimum 6.0% (Basel III §50).

    Args:
        tier1_capital: Tier 1 capital (CET1 + additional Tier 1).
        risk_weighted_assets: Total risk-weighted assets.

    Returns:
        Dict with ``tier1_ratio`` (decimal), ``minimum``, ``surplus`` and
        ``compliant``.

    Raises:
        ValueError: If RWA is non-positive.
    """
    if risk_weighted_assets <= 0.0:
        raise ValueError("risk_weighted_assets must be positive")
    ratio = tier1_capital / risk_weighted_assets
    return {
        "tier1_ratio": round(ratio, 8),
        "minimum": TIER1_MINIMUM,
        "surplus": round(ratio - TIER1_MINIMUM, 8),
        "compliant": bool(ratio >= TIER1_MINIMUM),
    }


def basel_iii_total_capital_ratio(
    total_capital: float,
    risk_weighted_assets: float,
) -> dict:  # type: ignore[type-arg]
    """Basel III Total capital ratio.

    ``Total ratio = (Tier 1 + Tier 2) / RWA``; minimum 8.0% (Basel III §50).

    Args:
        total_capital: Total regulatory capital (Tier 1 + Tier 2).
        risk_weighted_assets: Total risk-weighted assets.

    Returns:
        Dict with ``total_capital_ratio`` (decimal), ``minimum``, ``surplus``
        and ``compliant``.

    Raises:
        ValueError: If RWA is non-positive.
    """
    if risk_weighted_assets <= 0.0:
        raise ValueError("risk_weighted_assets must be positive")
    ratio = total_capital / risk_weighted_assets
    return {
        "total_capital_ratio": round(ratio, 8),
        "minimum": TOTAL_CAPITAL_MINIMUM,
        "surplus": round(ratio - TOTAL_CAPITAL_MINIMUM, 8),
        "compliant": bool(ratio >= TOTAL_CAPITAL_MINIMUM),
    }


def basel_iii_leverage_ratio(
    tier1_capital: float,
    total_exposure: float,
) -> dict:  # type: ignore[type-arg]
    """Basel III leverage ratio.

    ``Leverage ratio = Tier 1 capital / total exposure measure``; minimum 3.0%.
    The exposure measure is non-risk-weighted (on + off balance sheet).

    Args:
        tier1_capital: Tier 1 capital.
        total_exposure: Total leverage exposure measure.

    Returns:
        Dict with ``leverage_ratio`` (decimal), ``minimum``, ``surplus`` and
        ``compliant``.

    Raises:
        ValueError: If total exposure is non-positive.
    """
    if total_exposure <= 0.0:
        raise ValueError("total_exposure must be positive")
    ratio = tier1_capital / total_exposure
    return {
        "leverage_ratio": round(ratio, 8),
        "minimum": LEVERAGE_RATIO_MINIMUM,
        "surplus": round(ratio - LEVERAGE_RATIO_MINIMUM, 8),
        "compliant": bool(ratio >= LEVERAGE_RATIO_MINIMUM),
    }


def basel_iv_output_floor(
    internal_model_rwa: float,
    standardised_rwa: float,
    floor_factor: float = OUTPUT_FLOOR_FACTOR,
) -> dict:  # type: ignore[type-arg]
    """Basel IV output floor.

    Floored RWA = ``max(internal_model_rwa, floor_factor * standardised_rwa)``.
    The floor factor is 72.5% (Basel III finalisation) — do not relax.

    Args:
        internal_model_rwa: RWA from internal models.
        standardised_rwa: RWA under the standardised approach.
        floor_factor: Output floor factor (default 0.725, regulatory).

    Returns:
        Dict with ``floored_rwa``, ``floor_rwa`` (the 72.5% floor), the
        ``binding`` flag and the ``rwa_uplift`` from the floor.

    Raises:
        ValueError: If either RWA is negative or floor_factor not in [0, 1].
    """
    if internal_model_rwa < 0.0 or standardised_rwa < 0.0:
        raise ValueError("RWA values must be non-negative")
    if not 0.0 <= floor_factor <= 1.0:
        raise ValueError("floor_factor must be in [0, 1]")
    floor_rwa = floor_factor * standardised_rwa
    floored = max(internal_model_rwa, floor_rwa)
    return {
        "floored_rwa": round(floored, 4),
        "floor_rwa": round(floor_rwa, 4),
        "binding": bool(floor_rwa > internal_model_rwa),
        "rwa_uplift": round(floored - internal_model_rwa, 4),
        "floor_factor": floor_factor,
    }


def icaap_capital_assessment(
    pillar1_capital: float,
    risk_capital_components: np.ndarray,
    available_capital: float,
) -> dict:  # type: ignore[type-arg]
    """ICAAP internal capital adequacy assessment.

    Aggregates Pillar 1 capital with internally-assessed risk components
    (credit concentration, IRRBB, etc.) and compares to available capital.

    Args:
        pillar1_capital: Pillar 1 minimum capital requirement.
        risk_capital_components: Array of additional internal risk capital
            charges (Pillar 2 risk types).
        available_capital: Total available own funds.

    Returns:
        Dict with ``total_capital_requirement``, ``available_capital``,
        ``capital_surplus`` and ``adequate``.

    Raises:
        ValueError: If pillar1_capital is negative.
    """
    if pillar1_capital < 0.0:
        raise ValueError("pillar1_capital must be non-negative")
    components = np.asarray(risk_capital_components, dtype=np.float64)
    pillar2 = float(np.sum(components))
    total_req = pillar1_capital + pillar2
    surplus = available_capital - total_req
    return {
        "total_capital_requirement": round(total_req, 4),
        "pillar2_capital": round(pillar2, 4),
        "available_capital": round(float(available_capital), 4),
        "capital_surplus": round(surplus, 4),
        "adequate": bool(surplus >= 0.0),
    }


def srep_capital_add_on(
    pillar1_requirement: float,
    pillar2a_addon_ratio: float,
    risk_weighted_assets: float,
) -> dict:  # type: ignore[type-arg]
    """SREP (Supervisory Review and Evaluation Process) capital add-on.

    Translates the supervisory Pillar 2A add-on ratio into a capital amount and
    the Total SREP Capital Requirement (TSCR).

    Args:
        pillar1_requirement: Pillar 1 capital requirement (currency).
        pillar2a_addon_ratio: Pillar 2A add-on as a fraction of RWA.
        risk_weighted_assets: Total risk-weighted assets.

    Returns:
        Dict with ``pillar2a_capital``, ``total_srep_requirement`` (TSCR) and
        the implied ``tscr_ratio``.

    Raises:
        ValueError: If RWA is non-positive or the add-on ratio is negative.
    """
    if risk_weighted_assets <= 0.0:
        raise ValueError("risk_weighted_assets must be positive")
    if pillar2a_addon_ratio < 0.0:
        raise ValueError("pillar2a_addon_ratio must be non-negative")
    p2a_capital = pillar2a_addon_ratio * risk_weighted_assets
    tscr = pillar1_requirement + p2a_capital
    return {
        "pillar2a_capital": round(p2a_capital, 4),
        "total_srep_requirement": round(tscr, 4),
        "tscr_ratio": round(tscr / risk_weighted_assets, 8),
    }


def pillar_2a_capital(
    risk_addons: np.ndarray,
    risk_weighted_assets: float,
) -> dict:  # type: ignore[type-arg]
    """Pillar 2A capital — sum of individual risk add-ons.

    Pillar 2A covers risks not (fully) captured in Pillar 1: e.g. credit
    concentration, IRRBB, pension, operational. Sums the component charges.

    Args:
        risk_addons: Array of per-risk capital add-ons (currency).
        risk_weighted_assets: Total risk-weighted assets (for the ratio).

    Returns:
        Dict with ``pillar2a_capital`` and the ``pillar2a_ratio`` of RWA.

    Raises:
        ValueError: If RWA is non-positive.
    """
    if risk_weighted_assets <= 0.0:
        raise ValueError("risk_weighted_assets must be positive")
    addons = np.asarray(risk_addons, dtype=np.float64)
    total = float(np.sum(addons))
    return {
        "pillar2a_capital": round(total, 4),
        "pillar2a_ratio": round(total / risk_weighted_assets, 8),
        "n_components": int(addons.size),
    }


def pillar_2b_stress_buffer(
    stressed_capital_depletion: float,
    risk_weighted_assets: float,
) -> dict:  # type: ignore[type-arg]
    """Pillar 2B stress buffer (PRA buffer / capital guidance).

    The forward-looking buffer to absorb the peak capital depletion projected
    under the supervisory stress scenario.

    Args:
        stressed_capital_depletion: Peak CET1 depletion under stress (currency).
        risk_weighted_assets: Total risk-weighted assets.

    Returns:
        Dict with ``pillar2b_buffer`` (floored at zero) and the ``buffer_ratio``.

    Raises:
        ValueError: If RWA is non-positive.
    """
    if risk_weighted_assets <= 0.0:
        raise ValueError("risk_weighted_assets must be positive")
    buffer = max(stressed_capital_depletion, 0.0)
    return {
        "pillar2b_buffer": round(buffer, 4),
        "buffer_ratio": round(buffer / risk_weighted_assets, 8),
    }


def combined_buffer_requirement(
    capital_conservation_buffer_ratio: float = CAPITAL_CONSERVATION_BUFFER,
    countercyclical_buffer_ratio: float = 0.0,
    systemic_buffer_ratio: float = 0.0,
    risk_weighted_assets: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Combined Buffer Requirement (CBR).

    ``CBR = CCoB + CCyB + max(G-SII, O-SII, SyRB)`` per CRD IV. Sums the buffer
    ratios and (optionally) the capital amount on the supplied RWA.

    Args:
        capital_conservation_buffer_ratio: CCoB ratio (default 2.5%).
        countercyclical_buffer_ratio: Institution-specific CCyB ratio.
        systemic_buffer_ratio: Higher of systemic buffers (G-SII/O-SII/SyRB).
        risk_weighted_assets: RWA to convert the buffer ratio to capital.

    Returns:
        Dict with ``combined_buffer_ratio`` and (if RWA > 0) the
        ``combined_buffer_capital``.

    Raises:
        ValueError: If any buffer ratio is negative.
    """
    if (
        min(
            capital_conservation_buffer_ratio,
            countercyclical_buffer_ratio,
            systemic_buffer_ratio,
        )
        < 0.0
    ):
        raise ValueError("buffer ratios must be non-negative")
    cbr_ratio = (
        capital_conservation_buffer_ratio + countercyclical_buffer_ratio + systemic_buffer_ratio
    )
    result = {"combined_buffer_ratio": round(cbr_ratio, 8)}
    if risk_weighted_assets > 0.0:
        result["combined_buffer_capital"] = round(cbr_ratio * risk_weighted_assets, 4)
    return result


def capital_conservation_buffer(
    cet1_ratio: float,
    risk_weighted_assets: float,
    buffer_ratio: float = CAPITAL_CONSERVATION_BUFFER,
) -> dict:  # type: ignore[type-arg]
    """Capital Conservation Buffer (CCoB) and distribution constraint.

    The 2.5% CET1 buffer above the 4.5% minimum. Breaching the buffer triggers
    Maximum Distributable Amount (MDA) restrictions on dividends/bonuses.

    Args:
        cet1_ratio: Current CET1 ratio (decimal).
        risk_weighted_assets: Total risk-weighted assets.
        buffer_ratio: CCoB ratio (default 2.5%, regulatory).

    Returns:
        Dict with ``required_cet1_ratio`` (4.5% + buffer),
        ``buffer_capital``, ``buffer_met`` and the ``mda_restricted`` flag.

    Raises:
        ValueError: If RWA is non-positive.
    """
    if risk_weighted_assets <= 0.0:
        raise ValueError("risk_weighted_assets must be positive")
    required = CET1_MINIMUM + buffer_ratio
    return {
        "required_cet1_ratio": round(required, 8),
        "buffer_capital": round(buffer_ratio * risk_weighted_assets, 4),
        "buffer_met": bool(cet1_ratio >= required),
        "mda_restricted": bool(cet1_ratio < required),
    }


def countercyclical_capital_buffer(
    exposure_amounts: np.ndarray,
    country_ccyb_rates: np.ndarray,
    risk_weighted_assets: float,
) -> dict:  # type: ignore[type-arg]
    """Institution-specific Countercyclical Capital Buffer (CCyB).

    The CCyB rate is the exposure-weighted average of the national CCyB rates
    applied to the bank's private-sector credit exposures (CRD IV Art. 140).

    Args:
        exposure_amounts: Private-sector credit exposure per jurisdiction.
        country_ccyb_rates: National CCyB rate per jurisdiction (decimal).
        risk_weighted_assets: Total risk-weighted assets.

    Returns:
        Dict with ``ccyb_rate`` (weighted average) and the ``ccyb_capital``.

    Raises:
        ValueError: If arrays differ in length / are empty, or RWA non-positive.
    """
    exp = np.asarray(exposure_amounts, dtype=np.float64)
    rates = np.asarray(country_ccyb_rates, dtype=np.float64)
    if exp.size == 0 or exp.size != rates.size:
        raise ValueError("exposure/rate arrays must be non-empty and equal length")
    if risk_weighted_assets <= 0.0:
        raise ValueError("risk_weighted_assets must be positive")
    total_exp = float(np.sum(exp))
    ccyb_rate = float(np.sum(exp * rates) / total_exp) if total_exp > 0.0 else 0.0
    return {
        "ccyb_rate": round(ccyb_rate, 8),
        "ccyb_capital": round(ccyb_rate * risk_weighted_assets, 4),
    }


def crr2_large_exposure_limit(
    exposure_value: float,
    tier1_capital: float,
    is_institution: bool = False,
) -> dict:  # type: ignore[type-arg]
    """CRR2 large exposure limit (Art. 395).

    A single client / group exposure must not exceed 25% of Tier 1 capital
    (or EUR 150m for institutions, whichever is higher — simplified to the 25%
    ratio test here). Reports the exposure ratio and any breach amount.

    Args:
        exposure_value: Exposure value to a single client/group (post-CRM).
        tier1_capital: Tier 1 capital.
        is_institution: Whether the counterparty is an institution (affects the
            absolute alternative limit; not applied in this ratio test).

    Returns:
        Dict with ``exposure_ratio`` (of Tier 1), ``limit`` (25%),
        ``within_limit`` and the ``excess`` over the limit (currency).

    Raises:
        ValueError: If Tier 1 capital is non-positive.
    """
    if tier1_capital <= 0.0:
        raise ValueError("tier1_capital must be positive")
    ratio = exposure_value / tier1_capital
    limit_amount = LARGE_EXPOSURE_LIMIT * tier1_capital
    excess = max(exposure_value - limit_amount, 0.0)
    return {
        "exposure_ratio": round(ratio, 8),
        "limit": LARGE_EXPOSURE_LIMIT,
        "within_limit": bool(ratio <= LARGE_EXPOSURE_LIMIT),
        "excess": round(excess, 4),
        "is_institution": is_institution,
    }

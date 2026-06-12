"""engine/oprisk_capital.py — OpRisk regulatory and economic capital.

Implements the Basel Standardised Measurement Approach (SMA), capital allocation
across business lines, the diversification benefit, economic capital, insurance
mitigation offset, and the tail-risk / stress-testing capital adjustments.

The SMA Business-Indicator-Component is a deterministic piecewise-linear
formula and the allocation/diversification routines are light NumPy aggregation,
so no @njit kernels are required here (CLAUDE.md §3.1 guidance).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "basel_standardised_measurement_sma",
    "oprisk_capital_allocation",
    "diversification_benefit_oprisk",
    "oprisk_economic_capital",
    "insurance_offset_calculation",
    "tail_risk_scenario_oprisk",
    "oprisk_stress_testing",
]

# Basel SMA Business Indicator marginal coefficients and bucket thresholds
# (BCBS d424, "Minimum capital requirements for operational risk", 2017).
# Buckets in EUR: [0, 1bn], (1bn, 30bn], (>30bn]; coefficients 12%, 15%, 18%.
_SMA_BUCKET_1 = 1_000_000_000.0
_SMA_BUCKET_2 = 30_000_000_000.0
_SMA_COEF_1 = 0.12
_SMA_COEF_2 = 0.15
_SMA_COEF_3 = 0.18


def _business_indicator_component(bi: float) -> float:
    """Piecewise-linear SMA Business Indicator Component (BIC)."""
    if bi <= _SMA_BUCKET_1:
        return _SMA_COEF_1 * bi
    if bi <= _SMA_BUCKET_2:
        return _SMA_COEF_1 * _SMA_BUCKET_1 + _SMA_COEF_2 * (bi - _SMA_BUCKET_1)
    return (
        _SMA_COEF_1 * _SMA_BUCKET_1
        + _SMA_COEF_2 * (_SMA_BUCKET_2 - _SMA_BUCKET_1)
        + _SMA_COEF_3 * (bi - _SMA_BUCKET_2)
    )


def basel_standardised_measurement_sma(
    business_indicator: float,
    loss_component: float = 0.0,
    use_ilm: bool = True,
) -> dict:  # type: ignore[type-arg]
    """Basel III Standardised Measurement Approach (SMA) capital.

    SMA capital = BIC × ILM, where the Business Indicator Component (BIC) is a
    piecewise-linear function of the Business Indicator (12%/15%/18% marginal
    coefficients across the three buckets) and the Internal Loss Multiplier
    (ILM) scales by the bank's historical loss experience:
    ``ILM = ln(e − 1 + (LC / BIC)^0.8)``. Bucket-1 banks may set ILM = 1.

    Args:
        business_indicator: Business Indicator (BI) in base currency.
        loss_component: Loss Component (15 × average annual losses).
        use_ilm: If False (or BI in bucket 1) the ILM is fixed at 1.0.

    Returns:
        Dict with ``bic``, ``ilm`` and ``sma_capital``.

    Raises:
        ValueError: If ``business_indicator`` is negative.
    """
    if business_indicator < 0:
        raise ValueError("business_indicator must be non-negative")

    bic = _business_indicator_component(business_indicator)
    if not use_ilm or business_indicator <= _SMA_BUCKET_1 or bic <= 0:
        ilm = 1.0
    else:
        ratio = loss_component / bic
        ilm = float(np.log(np.e - 1.0 + ratio**0.8))
        ilm = max(ilm, 0.0)
    capital = bic * ilm
    return {
        "bic": round(float(bic), 2),
        "ilm": round(float(ilm), 6),
        "sma_capital": round(float(capital), 2),
    }


def oprisk_capital_allocation(
    total_capital: float,
    business_line_risks: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Allocate total OpRisk capital across business lines (pro-rata by risk).

    Distributes the firm-wide capital to business lines in proportion to their
    standalone risk contributions, so the allocations sum exactly to the total —
    a coherent (additive) allocation.

    Args:
        total_capital: Firm-wide OpRisk capital to allocate.
        business_line_risks: Standalone risk measure per business line.

    Returns:
        Dict with ``allocations`` (per line) and ``shares``.

    Raises:
        ValueError: If risks are empty / negative or sum to zero.
    """
    risks = np.asarray(business_line_risks, dtype=np.float64)
    if risks.size == 0 or np.any(risks < 0):
        raise ValueError("business_line_risks must be non-empty and non-negative")
    total_risk = float(np.sum(risks))
    if total_risk <= 0:
        raise ValueError("sum of business_line_risks must be positive")

    shares = risks / total_risk
    allocations = shares * total_capital
    return {
        "allocations": [round(float(a), 2) for a in allocations],
        "shares": [round(float(s), 6) for s in shares],
    }


def diversification_benefit_oprisk(
    standalone_capitals: np.ndarray,
    correlation: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Diversification benefit across OpRisk cells under a single correlation.

    Compares the simple sum of standalone capitals (perfect-correlation, no
    diversification) with the correlated aggregate
    ``sqrt(sum_i sum_j rho_ij K_i K_j)`` using a uniform pairwise correlation.
    The benefit is the reduction from imperfect correlation.

    Args:
        standalone_capitals: Standalone capital per OpRisk cell (>= 0).
        correlation: Uniform pairwise correlation in [0, 1] (0 = independent).

    Returns:
        Dict with ``sum_standalone``, ``diversified_capital`` and
        ``diversification_benefit`` (>= 0).

    Raises:
        ValueError: If capitals are negative or correlation lies outside [0, 1].
    """
    k = np.asarray(standalone_capitals, dtype=np.float64)
    if k.size == 0 or np.any(k < 0):
        raise ValueError("standalone_capitals must be non-empty and non-negative")
    if not 0.0 <= correlation <= 1.0:
        raise ValueError("correlation must lie in [0, 1]")

    n = k.size
    corr = np.full((n, n), correlation, dtype=np.float64)
    np.fill_diagonal(corr, 1.0)
    diversified = float(np.sqrt(k @ corr @ k))
    total = float(np.sum(k))
    benefit = total - diversified
    return {
        "sum_standalone": round(total, 2),
        "diversified_capital": round(diversified, 2),
        "diversification_benefit": round(max(benefit, 0.0), 2),
    }


def oprisk_economic_capital(
    opvar: float,
    expected_loss: float,
    insurance_offset: float = 0.0,
    diversification_benefit: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """OpRisk economic capital (unexpected loss net of mitigants).

    Economic capital is the unexpected loss (OpVaR − expected loss) reduced by
    recognised risk mitigants (insurance recoveries and diversification), floored
    at zero.

    Args:
        opvar: Operational VaR at the economic-capital confidence.
        expected_loss: Expected annual loss.
        insurance_offset: Recognised insurance mitigation.
        diversification_benefit: Recognised diversification benefit.

    Returns:
        Dict with ``gross_capital`` (UL), ``economic_capital`` (net) and
        ``total_mitigation``.

    Raises:
        ValueError: If any mitigant is negative.
    """
    if insurance_offset < 0 or diversification_benefit < 0:
        raise ValueError("mitigants must be non-negative")
    gross = max(opvar - expected_loss, 0.0)
    mitigation = insurance_offset + diversification_benefit
    economic = max(gross - mitigation, 0.0)
    return {
        "gross_capital": round(float(gross), 2),
        "economic_capital": round(float(economic), 2),
        "total_mitigation": round(float(mitigation), 2),
    }


def insurance_offset_calculation(
    gross_loss: float,
    policy_limit: float,
    deductible: float,
    haircut: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Insurance mitigation offset for an operational loss.

    Recoverable amount = ``min(max(gross_loss − deductible, 0), policy_limit)``
    reduced by a supervisory haircut (Basel caps total insurance recognition at
    20% of capital and applies haircuts for residual term and payment
    uncertainty; the cap is applied by the caller).

    Args:
        gross_loss: Gross operational loss.
        policy_limit: Maximum insurance pay-out.
        deductible: Loss retained by the firm before insurance responds.
        haircut: Supervisory haircut on the recovery, in [0, 1].

    Returns:
        Dict with ``recoverable`` (post-haircut), ``net_loss`` and
        ``recovery_rate``.

    Raises:
        ValueError: If inputs are negative or haircut is out of range.
    """
    if gross_loss < 0 or policy_limit < 0 or deductible < 0:
        raise ValueError("loss/limit/deductible must be non-negative")
    if not 0.0 <= haircut <= 1.0:
        raise ValueError("haircut must lie in [0, 1]")

    above_deductible = max(gross_loss - deductible, 0.0)
    capped = min(above_deductible, policy_limit)
    recoverable = capped * (1.0 - haircut)
    net_loss = gross_loss - recoverable
    rate = recoverable / gross_loss if gross_loss > 0 else 0.0
    return {
        "recoverable": round(float(recoverable), 2),
        "net_loss": round(float(net_loss), 2),
        "recovery_rate": round(float(rate), 6),
    }


def tail_risk_scenario_oprisk(
    annual_losses: np.ndarray,
    tail_confidence: float = 0.999,
    severity_multiplier: float = 1.0,
) -> dict:  # type: ignore[type-arg]
    """Tail-risk scenario capital uplift for OpRisk.

    Stresses the extreme tail by scaling losses beyond the tail quantile by a
    ``severity_multiplier`` (e.g. a "perfect-storm" amplification) and re-reading
    the stressed tail expectation. Reports the uplift over the unstressed tail.

    Args:
        annual_losses: Sample of aggregate annual losses.
        tail_confidence: Tail quantile defining "extreme" losses.
        severity_multiplier: Multiplier applied to tail losses (>= 1.0).

    Returns:
        Dict with ``base_tail_es``, ``stressed_tail_es`` and ``capital_uplift``.

    Raises:
        ValueError: If the sample is empty or multiplier < 1.
    """
    losses = np.asarray(annual_losses, dtype=np.float64)
    if losses.size == 0:
        raise ValueError("annual_losses must be non-empty")
    if severity_multiplier < 1.0:
        raise ValueError("severity_multiplier must be >= 1.0")
    if not 0.90 <= tail_confidence <= 0.9999:
        raise ValueError("tail_confidence must lie in [0.90, 0.9999]")

    sorted_losses = np.sort(losses)
    n = sorted_losses.size
    idx = min(int(np.floor(tail_confidence * n)), n - 1)
    base_es = float(np.mean(sorted_losses[idx:]))
    stressed_es = base_es * severity_multiplier
    return {
        "base_tail_es": round(base_es, 2),
        "stressed_tail_es": round(stressed_es, 2),
        "capital_uplift": round(stressed_es - base_es, 2),
    }


def oprisk_stress_testing(
    base_capital: float,
    frequency_shock: float,
    severity_shock: float,
) -> dict:  # type: ignore[type-arg]
    """OpRisk stress-testing capital projection.

    Projects stressed capital by scaling the base capital for shocks to event
    frequency and severity. Because aggregate loss scales (approximately)
    multiplicatively in both drivers, stressed capital =
    ``base × (1 + freq_shock) × (1 + sev_shock)``.

    Args:
        base_capital: Baseline OpRisk capital.
        frequency_shock: Fractional increase in event frequency (>= -1).
        severity_shock: Fractional increase in event severity (>= -1).

    Returns:
        Dict with ``stressed_capital`` and ``capital_increase`` (absolute).

    Raises:
        ValueError: If a shock is below -1 (would imply negative driver).
    """
    if frequency_shock < -1.0 or severity_shock < -1.0:
        raise ValueError("shocks must be >= -1.0")
    stressed = base_capital * (1.0 + frequency_shock) * (1.0 + severity_shock)
    return {
        "stressed_capital": round(float(stressed), 2),
        "capital_increase": round(float(stressed - base_capital), 2),
    }

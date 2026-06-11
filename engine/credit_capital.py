"""engine/credit_capital.py — Basel IRB & Standardised regulatory capital.

Implements the regulatory-capital sub-domain: the Basel III IRB risk-weight
function (foundation and advanced), the Standardised Approach RWA, the IRB
maturity adjustment and the asset/SME correlation factor.

The IRB formulas follow the Basel Committee framework (CRE31 / CRR Art. 153-154)
exactly — these are ``[REGULATORY]`` and must not be simplified:

  Correlation (corporate):
      R = 0.12 * (1 - e^{-50*PD})/(1 - e^{-50}) + 0.24 * (1 - (1 - e^{-50*PD})/(1 - e^{-50}))

  Maturity adjustment:
      b = (0.11852 - 0.05478 * ln(PD))^2
      MA = (1 + (M - 2.5) * b) / (1 - 1.5 * b)

  Capital requirement K:
      K = [ LGD * N( (N^{-1}(PD) + sqrt(R)*N^{-1}(0.999)) / sqrt(1-R) )
            - PD * LGD ] * MA
      RWA = K * 12.5 * EAD

Numba rules (CLAUDE.md §3.1): the heavy Gaussian-copula transform is pure
SciPy/NumPy in the public layer; small loop-carried kernels are JIT-compiled.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy import stats

__all__ = [
    "irb_foundation_approach_capital",
    "irb_advanced_approach_capital",
    "basel_standardised_approach_rwa",
    "maturity_adjustment_basel_irb",
    "sme_correlation_factor_basel",
]

# Basel one-factor model confidence level (CRE31): 99.9%.
_BASEL_CONFIDENCE = 0.999
_RWA_FACTOR = 12.5  # = 1 / 0.08 (8% minimum capital ratio).


@njit(cache=True)
def _basel_correlation(pd: float) -> float:
    """Basel corporate asset correlation R(PD) (CRE31.4).

    R = 0.12 * w + 0.24 * (1 - w), with w = (1 - e^{-50*PD})/(1 - e^{-50}).
    """
    denom = 1.0 - np.exp(-50.0)
    w = (1.0 - np.exp(-50.0 * pd)) / denom
    return 0.12 * w + 0.24 * (1.0 - w)


@njit(cache=True)
def _maturity_b(pd: float) -> float:
    """Maturity-adjustment slope b(PD) (CRE31.6)."""
    val = 0.11852 - 0.05478 * np.log(pd)
    return val * val


def _capital_k(
    pd: float, lgd: float, maturity: float, correlation: float
) -> tuple[float, float]:
    """Core IRB conditional-expected-loss capital requirement K.

    Returns ``(K, maturity_adjustment)``. Kept in pure Python because it relies
    on SciPy's inverse-normal (RULE 3: no Numba random/special functions).
    """
    n_inv_pd = float(stats.norm.ppf(pd))
    n_inv_conf = float(stats.norm.ppf(_BASEL_CONFIDENCE))
    conditional = (n_inv_pd + np.sqrt(correlation) * n_inv_conf) / np.sqrt(1.0 - correlation)
    conditional_pd = float(stats.norm.cdf(conditional))

    b = _maturity_b(pd)
    maturity_adj = (1.0 + (maturity - 2.5) * b) / (1.0 - 1.5 * b)
    k = (lgd * conditional_pd - pd * lgd) * maturity_adj
    return float(max(k, 0.0)), float(maturity_adj)


def _irb_capital(
    pd: float,
    lgd: float,
    ead: float,
    maturity: float,
    correlation: float | None,
) -> dict:  # type: ignore[type-arg]
    """Shared IRB risk-weight computation for F-IRB and A-IRB."""
    if not 0.0 < pd <= 1.0:
        raise ValueError("pd must be in (0, 1]")
    if not 0.0 <= lgd <= 1.0:
        raise ValueError("lgd must be in [0, 1]")
    if ead < 0.0:
        raise ValueError("ead must be non-negative")
    if maturity <= 0.0:
        raise ValueError("maturity must be positive")

    pd_eff = max(pd, 0.0003)  # Basel PD floor (3 bps).
    r = _basel_correlation(pd_eff) if correlation is None else correlation
    k, maturity_adj = _capital_k(pd_eff, lgd, maturity, r)
    rwa = k * _RWA_FACTOR * ead
    return {
        "k": round(k, 10),
        "rwa": round(rwa, 6),
        "capital_required": round(k * ead, 6),
        "risk_weight": round(k * _RWA_FACTOR, 10),
        "correlation": round(r, 10),
        "maturity_adjustment": round(maturity_adj, 10),
        "pd_used": round(pd_eff, 10),
    }


def irb_foundation_approach_capital(
    pd: float,
    ead: float,
    maturity: float = 2.5,
    lgd: float = 0.45,
    seniority: str = "senior_unsecured",
) -> dict:  # type: ignore[type-arg]
    """Basel IRB Foundation-Approach capital (CRE31).

    Under F-IRB the bank supplies its own PD but uses *supervisory* LGD: 45% for
    senior unsecured and 75% for subordinated claims (CRE32). EAD and maturity
    are also supervisory (M defaults to 2.5 years).

    Args:
        pd: Own-estimate probability of default in ``(0, 1]``.
        ead: Exposure at default (currency amount, >= 0).
        maturity: Effective maturity M in years (supervisory default 2.5).
        lgd: Override supervisory LGD; ignored unless ``seniority`` is custom.
        seniority: ``"senior_unsecured"`` (45%) or ``"subordinated"`` (75%).

    Returns:
        Dict with ``rwa``, capital requirement ``k`` (per unit EAD),
        ``capital_required`` (currency), ``risk_weight``, ``correlation`` and
        ``maturity_adjustment``.

    Raises:
        ValueError: If parameters are out of range or seniority is unknown.
    """
    if seniority == "senior_unsecured":
        lgd_used = 0.45
    elif seniority == "subordinated":
        lgd_used = 0.75
    elif seniority == "custom":
        lgd_used = lgd
    else:
        raise ValueError("seniority must be senior_unsecured, subordinated or custom")

    result = _irb_capital(pd, lgd_used, ead, maturity, correlation=None)
    result["approach"] = "F-IRB"
    result["lgd_used"] = lgd_used
    return result


def irb_advanced_approach_capital(
    pd: float,
    lgd: float,
    ead: float,
    maturity: float = 2.5,
    correlation: float | None = None,
) -> dict:  # type: ignore[type-arg]
    """Basel IRB Advanced-Approach capital (CRE31).

    Under A-IRB the bank supplies its own PD, LGD, EAD and effective maturity.
    The risk-weight function is identical to F-IRB; only the parameter sources
    differ.

    Args:
        pd: Own-estimate probability of default in ``(0, 1]``.
        lgd: Own-estimate loss given default in ``[0, 1]``.
        ead: Own-estimate exposure at default (>= 0).
        maturity: Own-estimate effective maturity M in years.
        correlation: Optional override of the asset correlation R (e.g. for an
            SME or specialised-lending adjustment); ``None`` uses the Basel
            corporate formula.

    Returns:
        Dict identical in shape to :func:`irb_foundation_approach_capital` with
        ``approach="A-IRB"``.

    Raises:
        ValueError: If parameters are out of range.
    """
    result = _irb_capital(pd, lgd, ead, maturity, correlation=correlation)
    result["approach"] = "A-IRB"
    result["lgd_used"] = lgd
    return result


def basel_standardised_approach_rwa(
    ead: float,
    risk_weight: float,
    credit_risk_mitigation: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Basel Standardised-Approach RWA (CRE20).

    ``RWA = (EAD - CRM) * risk_weight``, where the supervisory risk weight is
    set by the external rating / exposure class (e.g. 0% sovereign AAA, 20%
    bank, 100% corporate unrated, 150% sub-investment grade). The minimum
    capital is 8% of RWA.

    Args:
        ead: Exposure at default (currency amount, >= 0).
        risk_weight: Supervisory risk weight as a fraction (e.g. 1.0 for 100%).
        credit_risk_mitigation: Eligible collateral / guarantee value netted
            from EAD before weighting (>= 0).

    Returns:
        Dict with ``rwa``, ``capital_required`` (= 8% of RWA), ``net_exposure``
        and the applied ``risk_weight``.

    Raises:
        ValueError: If EAD, weight or CRM are negative or CRM exceeds EAD.
    """
    if ead < 0.0:
        raise ValueError("ead must be non-negative")
    if risk_weight < 0.0:
        raise ValueError("risk_weight must be non-negative")
    if credit_risk_mitigation < 0.0:
        raise ValueError("credit_risk_mitigation must be non-negative")

    net_exposure = max(ead - credit_risk_mitigation, 0.0)
    rwa = net_exposure * risk_weight
    return {
        "rwa": round(rwa, 6),
        "capital_required": round(rwa * 0.08, 6),
        "net_exposure": round(net_exposure, 6),
        "risk_weight": risk_weight,
    }


def maturity_adjustment_basel_irb(
    pd: float,
    maturity: float,
) -> dict:  # type: ignore[type-arg]
    """Basel IRB maturity adjustment (CRE31.6).

    ``b(PD) = (0.11852 - 0.05478 ln PD)^2`` and
    ``MA = (1 + (M - 2.5) b) / (1 - 1.5 b)``. At M = 2.5 the adjustment is
    exactly 1.0 by construction.

    Args:
        pd: Probability of default in ``(0, 1]``.
        maturity: Effective maturity M in years (Basel caps M at 5, floors at 1
            for most exposures; not enforced here so the raw factor is exposed).

    Returns:
        Dict with ``maturity_adjustment`` and the slope ``b``.

    Raises:
        ValueError: If PD is out of range or maturity is non-positive.
    """
    if not 0.0 < pd <= 1.0:
        raise ValueError("pd must be in (0, 1]")
    if maturity <= 0.0:
        raise ValueError("maturity must be positive")

    pd_eff = max(pd, 0.0003)
    b = _maturity_b(pd_eff)
    ma = (1.0 + (maturity - 2.5) * b) / (1.0 - 1.5 * b)
    return {
        "maturity_adjustment": round(float(ma), 10),
        "b": round(float(b), 10),
        "pd_used": round(pd_eff, 10),
        "maturity": maturity,
    }


def sme_correlation_factor_basel(
    pd: float,
    annual_sales_millions: float,
) -> dict:  # type: ignore[type-arg]
    """Basel SME firm-size correlation adjustment (CRE31.10).

    For SME corporate exposures (sales €5m-€50m) the asset correlation is
    reduced by a size term:
    ``R_SME = R_corp - 0.04 * (1 - (S - 5)/45)`` with S clamped to ``[5, 50]``.
    This lowers the capital charge for smaller, more idiosyncratic borrowers.

    Args:
        pd: Probability of default in ``(0, 1]``.
        annual_sales_millions: Total annual sales S in € millions.

    Returns:
        Dict with ``correlation_sme``, the un-adjusted ``correlation_corporate``
        and the applied firm-size term ``size_adjustment``.

    Raises:
        ValueError: If PD is out of range or sales are negative.
    """
    if not 0.0 < pd <= 1.0:
        raise ValueError("pd must be in (0, 1]")
    if annual_sales_millions < 0.0:
        raise ValueError("annual_sales_millions must be non-negative")

    pd_eff = max(pd, 0.0003)
    r_corp = _basel_correlation(pd_eff)
    s = min(max(annual_sales_millions, 5.0), 50.0)
    size_adj = 0.04 * (1.0 - (s - 5.0) / 45.0)
    r_sme = r_corp - size_adj
    return {
        "correlation_sme": round(float(r_sme), 10),
        "correlation_corporate": round(float(r_corp), 10),
        "size_adjustment": round(float(size_adj), 10),
        "sales_used": s,
    }

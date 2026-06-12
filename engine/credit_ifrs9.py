"""engine/credit_ifrs9.py — IFRS 9 ECL, portfolio optimisation and stress testing.

Implements the accounting-provisioning sub-domain plus two portfolio-level
functions:
  * IFRS 9 stage classification (PD-threshold rule), 12-month ECL (Stage 1),
    lifetime ECL (Stage 2/3), scenario-weighted ECL, macroeconomic overlays and
    a full staging-criteria assessment;
  * credit portfolio optimisation (return per unit of expected loss);
  * credit stress testing (PD/LGD multiplicative shocks on the loss profile).

IFRS 9 staging follows the significant-increase-in-credit-risk (SICR) test:
Stage 1 = no SICR; Stage 2 = SICR but not credit-impaired; Stage 3 = credit
impaired (default). ECL = sum over scenarios of probability-weighted
``PD * LGD * EAD * discount``; 12-month vs lifetime differ by the PD horizon.

Numba rules (CLAUDE.md §3.1): the lifetime-ECL discounted summation kernel is
JIT-compiled and returns NumPy arrays; classification logic is pure Python.
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "ifrs_9_stage_classification_pd_threshold",
    "ifrs_9_12_month_ecl_stage_1",
    "ifrs_9_lifetime_ecl_stage_2_3",
    "ifrs_9_scenario_weighted_ecl",
    "macroeconomic_overlays_ecl",
    "ifrs_9_staging_criteria_assessment",
    "credit_portfolio_optimisation",
    "credit_stress_testing",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _lifetime_ecl(
    marginal_pd: np.ndarray,
    lgd: np.ndarray,
    ead: np.ndarray,
    discount: np.ndarray,
) -> float:
    """Discounted lifetime ECL = sum_t marginal_PD_t * LGD_t * EAD_t * DF_t."""
    n = marginal_pd.shape[0]
    total = 0.0
    for t in range(n):
        total += marginal_pd[t] * lgd[t] * ead[t] * discount[t]
    return total


# ── Public functions ─────────────────────────────────────────────────────────


def ifrs_9_stage_classification_pd_threshold(
    pd_current: float,
    pd_origination: float,
    days_past_due: int = 0,
    sicr_relative_threshold: float = 2.0,
    sicr_absolute_threshold: float = 0.02,
) -> dict:  # type: ignore[type-arg]
    """IFRS 9 stage classification by the PD-threshold SICR rule.

    Stage 3 if credit-impaired (90+ days past due, the IFRS 9 rebuttable default
    presumption). Otherwise Stage 2 if a significant increase in credit risk has
    occurred — either the lifetime PD has risen by at least
    ``sicr_relative_threshold`` times origination, OR the absolute PD increase
    exceeds ``sicr_absolute_threshold``. Else Stage 1.

    Args:
        pd_current: Current (reporting-date) lifetime PD in ``[0, 1]``.
        pd_origination: Lifetime PD at initial recognition in ``[0, 1]``.
        days_past_due: Days the exposure is past due (>= 0).
        sicr_relative_threshold: Relative PD multiple triggering SICR (>= 1).
        sicr_absolute_threshold: Absolute PD increase triggering SICR.

    Returns:
        Dict with ``stage`` (1/2/3), the ``sicr`` flag and the trigger reason.

    Raises:
        ValueError: If PDs are out of range or thresholds invalid.
    """
    if not 0.0 <= pd_current <= 1.0 or not 0.0 <= pd_origination <= 1.0:
        raise ValueError("PDs must lie in [0, 1]")
    if days_past_due < 0:
        raise ValueError("days_past_due must be non-negative")
    if sicr_relative_threshold < 1.0:
        raise ValueError("sicr_relative_threshold must be >= 1")

    if days_past_due >= 90:
        return {"stage": 3, "sicr": True, "reason": "credit_impaired_90dpd"}

    relative_trigger = pd_origination > 0.0 and (
        pd_current >= sicr_relative_threshold * pd_origination
    )
    absolute_trigger = (pd_current - pd_origination) >= sicr_absolute_threshold
    if relative_trigger or absolute_trigger:
        reason = "relative_pd" if relative_trigger else "absolute_pd"
        return {"stage": 2, "sicr": True, "reason": reason}
    return {"stage": 1, "sicr": False, "reason": "no_sicr"}


def ifrs_9_12_month_ecl_stage_1(
    pd_12m: float,
    lgd: float,
    ead: float,
    discount_factor: float = 1.0,
) -> dict:  # type: ignore[type-arg]
    """IFRS 9 Stage 1 (12-month) Expected Credit Loss.

    For Stage 1 exposures ECL uses the 12-month PD:
    ``ECL = PD_12m * LGD * EAD * DF``.

    Args:
        pd_12m: 12-month probability of default in ``[0, 1]``.
        lgd: Loss given default in ``[0, 1]``.
        ead: Exposure at default (>= 0).
        discount_factor: Discount factor to the reporting date in ``(0, 1]``.

    Returns:
        Dict with ``ecl``, ``ecl_rate`` (= PD*LGD) and ``stage`` = 1.

    Raises:
        ValueError: If parameters are out of range.
    """
    if not 0.0 <= pd_12m <= 1.0 or not 0.0 <= lgd <= 1.0:
        raise ValueError("pd_12m and lgd must lie in [0, 1]")
    if ead < 0.0:
        raise ValueError("ead must be non-negative")
    if not 0.0 < discount_factor <= 1.0:
        raise ValueError("discount_factor must lie in (0, 1]")

    ecl = pd_12m * lgd * ead * discount_factor
    return {
        "ecl": round(ecl, 6),
        "ecl_rate": round(pd_12m * lgd, 10),
        "stage": 1,
    }


def ifrs_9_lifetime_ecl_stage_2_3(
    marginal_pd: np.ndarray,
    lgd: np.ndarray,
    ead: np.ndarray,
    discount_factors: np.ndarray,
    stage: int = 2,
) -> dict:  # type: ignore[type-arg]
    """IFRS 9 Stage 2/3 lifetime Expected Credit Loss.

    Lifetime ECL sums discounted expected loss across all future periods using
    the *marginal* (per-period) PD term structure:
    ``ECL = sum_t marginal_PD_t * LGD_t * EAD_t * DF_t``. For Stage 3 the PD is
    effectively 1 in the first period (already defaulted); callers pass the
    appropriate marginal-PD vector.

    Args:
        marginal_pd: ``(n,)`` per-period marginal default probabilities in
            ``[0, 1]`` (should sum to <= 1).
        lgd: ``(n,)`` per-period LGD in ``[0, 1]``.
        ead: ``(n,)`` per-period EAD (>= 0).
        discount_factors: ``(n,)`` discount factors in ``(0, 1]``.
        stage: Reported stage (2 or 3) for metadata.

    Returns:
        Dict with ``ecl``, ``cumulative_pd`` and the reported ``stage``.

    Raises:
        ValueError: If shapes mismatch, values out of range, or stage invalid.
    """
    mpd = np.asarray(marginal_pd, dtype=np.float64).ravel()
    lgd_arr = np.asarray(lgd, dtype=np.float64).ravel()
    e = np.asarray(ead, dtype=np.float64).ravel()
    df = np.asarray(discount_factors, dtype=np.float64).ravel()
    if not (mpd.shape == lgd_arr.shape == e.shape == df.shape) or mpd.size == 0:
        raise ValueError("all profile arrays must share the same non-empty shape")
    if np.any((mpd < 0.0) | (mpd > 1.0)) or np.any((lgd_arr < 0.0) | (lgd_arr > 1.0)):
        raise ValueError("marginal_pd and lgd must lie in [0, 1]")
    if np.any((df <= 0.0) | (df > 1.0)):
        raise ValueError("discount_factors must lie in (0, 1]")
    if stage not in (2, 3):
        raise ValueError("stage must be 2 or 3")

    ecl = _lifetime_ecl(mpd, lgd_arr, e, df)
    return {
        "ecl": round(float(ecl), 6),
        "cumulative_pd": round(float(np.sum(mpd)), 10),
        "stage": int(stage),
    }


def ifrs_9_scenario_weighted_ecl(
    scenario_ecls: np.ndarray,
    scenario_weights: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Probability-weighted ECL across forward-looking macro scenarios.

    IFRS 9 requires ECL to reflect an unbiased probability-weighted amount over
    multiple scenarios (base / upside / downside):
    ``ECL = sum_s weight_s * ECL_s`` with weights summing to 1.

    Args:
        scenario_ecls: ``(s,)`` ECL per scenario (>= 0).
        scenario_weights: ``(s,)`` scenario probabilities (>= 0, sum to ~1).

    Returns:
        Dict with ``ecl`` (weighted), per-scenario contributions ``contributions``
        and the normalised ``weights``.

    Raises:
        ValueError: If arrays mismatch, are empty, or weights sum to zero.
    """
    ecls = np.asarray(scenario_ecls, dtype=np.float64).ravel()
    w = np.asarray(scenario_weights, dtype=np.float64).ravel()
    if ecls.shape != w.shape or ecls.size == 0:
        raise ValueError("scenario_ecls and scenario_weights must match and be non-empty")
    if np.any(w < 0.0) or np.sum(w) <= 0.0:
        raise ValueError("scenario_weights must be non-negative and sum positive")
    if np.any(ecls < 0.0):
        raise ValueError("scenario_ecls must be non-negative")

    weights = w / np.sum(w)
    weighted = weights * ecls
    return {
        "ecl": round(float(np.sum(weighted)), 6),
        "contributions": [round(float(c), 6) for c in weighted],
        "weights": [round(float(x), 8) for x in weights],
    }


def macroeconomic_overlays_ecl(
    base_ecl: float,
    macro_factors: np.ndarray,
    sensitivities: np.ndarray,
    management_overlay: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Apply forward-looking macroeconomic overlays to a base ECL.

    Adjusts ECL for projected macro deviations via a multiplicative factor
    ``adj = 1 + sum_j sensitivity_j * factor_j`` (clamped at 0), then adds a
    discretionary management overlay. Captures the IFRS 9 requirement to
    incorporate forward-looking information not in the through-the-cycle model.

    Args:
        base_ecl: Model base-case ECL (>= 0).
        macro_factors: ``(k,)`` standardised macro deviations (e.g. GDP, unemp).
        sensitivities: ``(k,)`` ECL sensitivity (elasticity) to each factor.
        management_overlay: Additive post-model adjustment (can be negative).

    Returns:
        Dict with ``ecl_adjusted``, the ``macro_multiplier`` and the
        ``model_ecl`` (overlay-driven part before management overlay).

    Raises:
        ValueError: If arrays mismatch or base ECL is negative.
    """
    f = np.asarray(macro_factors, dtype=np.float64).ravel()
    s = np.asarray(sensitivities, dtype=np.float64).ravel()
    if f.shape != s.shape or f.size == 0:
        raise ValueError("macro_factors and sensitivities must match and be non-empty")
    if base_ecl < 0.0:
        raise ValueError("base_ecl must be non-negative")

    multiplier = max(1.0 + float(np.sum(f * s)), 0.0)
    model_ecl = base_ecl * multiplier
    adjusted = max(model_ecl + management_overlay, 0.0)
    return {
        "ecl_adjusted": round(adjusted, 6),
        "macro_multiplier": round(multiplier, 8),
        "model_ecl": round(model_ecl, 6),
    }


def ifrs_9_staging_criteria_assessment(
    pd_current: float,
    pd_origination: float,
    days_past_due: int = 0,
    forbearance: bool = False,
    watchlist: bool = False,
    sicr_relative_threshold: float = 2.0,
) -> dict:  # type: ignore[type-arg]
    """Full IFRS 9 staging assessment combining quantitative and qualitative SICR.

    Extends the PD-threshold rule with qualitative backstops required by IFRS 9:
    forbearance and internal watchlist status force at least Stage 2, while
    90+ days past due forces Stage 3. The final stage is the most severe of all
    triggered criteria.

    Args:
        pd_current: Current lifetime PD in ``[0, 1]``.
        pd_origination: Origination lifetime PD in ``[0, 1]``.
        days_past_due: Days past due (>= 0).
        forbearance: Whether the exposure is under forbearance measures.
        watchlist: Whether the exposure is on the internal watchlist.
        sicr_relative_threshold: Relative-PD SICR multiple (>= 1).

    Returns:
        Dict with the final ``stage``, the list of ``triggers`` and the
        ``quantitative_stage`` from the PD rule alone.

    Raises:
        ValueError: If PDs are out of range.
    """
    quant = ifrs_9_stage_classification_pd_threshold(
        pd_current,
        pd_origination,
        days_past_due,
        sicr_relative_threshold=sicr_relative_threshold,
    )
    stage = quant["stage"]
    triggers: list[str] = []
    if quant["sicr"]:
        triggers.append(quant["reason"])
    if days_past_due >= 90:
        stage = max(stage, 3)
        triggers.append("90dpd")
    if forbearance:
        stage = max(stage, 2)
        triggers.append("forbearance")
    if watchlist:
        stage = max(stage, 2)
        triggers.append("watchlist")
    if not triggers:
        triggers.append("none")
    return {
        "stage": int(stage),
        "triggers": triggers,
        "quantitative_stage": int(quant["stage"]),
    }


def credit_portfolio_optimisation(
    expected_returns: np.ndarray,
    expected_losses: np.ndarray,
    max_weight: float = 1.0,
    risk_aversion: float = 1.0,
) -> dict:  # type: ignore[type-arg]
    """Single-period credit-portfolio weight optimisation (return vs expected loss).

    Maximises a mean-EL utility ``sum_i w_i (r_i - risk_aversion * EL_i)`` subject
    to ``sum w = 1`` and ``0 <= w_i <= max_weight``. With these box + simplex
    constraints the solution is a greedy water-filling onto the highest
    risk-adjusted scores, which is the exact optimum for a linear objective.

    Args:
        expected_returns: ``(n,)`` per-asset expected returns.
        expected_losses: ``(n,)`` per-asset expected loss rates (>= 0).
        max_weight: Per-name concentration cap in ``(0, 1]``.
        risk_aversion: Penalty applied to expected loss (>= 0).

    Returns:
        Dict with optimal ``weights``, the achieved ``utility`` and the
        ``portfolio_el`` (weighted expected loss).

    Raises:
        ValueError: If arrays mismatch, max_weight invalid, or it cannot fill 1.
    """
    r = np.asarray(expected_returns, dtype=np.float64).ravel()
    el = np.asarray(expected_losses, dtype=np.float64).ravel()
    if r.shape != el.shape or r.size == 0:
        raise ValueError("expected_returns and expected_losses must match and be non-empty")
    if np.any(el < 0.0):
        raise ValueError("expected_losses must be non-negative")
    n = r.size
    if not 0.0 < max_weight <= 1.0:
        raise ValueError("max_weight must lie in (0, 1]")
    if max_weight * n < 1.0 - 1e-12:
        raise ValueError("max_weight too small to allocate full weight of 1")
    if risk_aversion < 0.0:
        raise ValueError("risk_aversion must be non-negative")

    score = r - risk_aversion * el
    order = np.argsort(-score)  # descending score
    weights = np.zeros(n, dtype=np.float64)
    remaining = 1.0
    for idx in order:
        alloc = min(max_weight, remaining)
        weights[idx] = alloc
        remaining -= alloc
        if remaining <= 1e-12:
            break
    utility = float(np.sum(weights * score))
    portfolio_el = float(np.sum(weights * el))
    return {
        "weights": [round(float(w), 8) for w in weights],
        "utility": round(utility, 8),
        "portfolio_el": round(portfolio_el, 8),
    }


def credit_stress_testing(
    pd: np.ndarray,
    lgd: np.ndarray,
    ead: np.ndarray,
    pd_shock_multiplier: float = 1.5,
    lgd_shock_multiplier: float = 1.2,
) -> dict:  # type: ignore[type-arg]
    """Credit stress test: multiplicative PD/LGD shocks on the loss profile.

    Applies a supervisory-style stress (e.g. EBA adverse scenario) by scaling
    PD and LGD, clipping to ``[0, 1]``, and reports the baseline vs stressed
    expected loss and the incremental impairment.

    Args:
        pd: ``(n,)`` baseline PD per exposure in ``[0, 1]``.
        lgd: ``(n,)`` baseline LGD per exposure in ``[0, 1]``.
        ead: ``(n,)`` EAD per exposure (>= 0).
        pd_shock_multiplier: Multiplier applied to PD under stress (>= 1).
        lgd_shock_multiplier: Multiplier applied to LGD under stress (>= 1).

    Returns:
        Dict with ``baseline_el``, ``stressed_el``, the ``incremental_loss`` and
        the ``stress_ratio`` (stressed / baseline).

    Raises:
        ValueError: If shapes mismatch, values out of range, or shocks < 1.
    """
    p = np.asarray(pd, dtype=np.float64).ravel()
    lgd_arr = np.asarray(lgd, dtype=np.float64).ravel()
    e = np.asarray(ead, dtype=np.float64).ravel()
    if not (p.shape == lgd_arr.shape == e.shape) or p.size == 0:
        raise ValueError("pd, lgd, ead must share the same non-empty shape")
    if np.any((p < 0.0) | (p > 1.0)) or np.any((lgd_arr < 0.0) | (lgd_arr > 1.0)):
        raise ValueError("pd and lgd must lie in [0, 1]")
    if np.any(e < 0.0):
        raise ValueError("ead must be non-negative")
    if pd_shock_multiplier < 1.0 or lgd_shock_multiplier < 1.0:
        raise ValueError("shock multipliers must be >= 1 (stress is adverse)")

    baseline = float(np.sum(p * lgd_arr * e))
    p_stress = np.clip(p * pd_shock_multiplier, 0.0, 1.0)
    l_stress = np.clip(lgd_arr * lgd_shock_multiplier, 0.0, 1.0)
    stressed = float(np.sum(p_stress * l_stress * e))
    ratio = stressed / baseline if baseline > 0.0 else 1.0
    return {
        "baseline_el": round(baseline, 6),
        "stressed_el": round(stressed, 6),
        "incremental_loss": round(stressed - baseline, 6),
        "stress_ratio": round(ratio, 8),
    }

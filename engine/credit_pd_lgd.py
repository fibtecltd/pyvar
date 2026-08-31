"""engine/credit_pd_lgd.py — Core credit-risk parameters (PD / LGD / EAD / EL / UL).

Implements the foundational risk-parameter sub-domain of the Credit Risk
function set: probability of default, loss given default, exposure at default,
expected and unexpected loss, recovery-rate estimation and the Basel downturn
LGD adjustment.

Numba rules (CLAUDE.md §3.1) are honoured exactly:
  * ``@njit`` kernels are stateless, take only float64 arrays / scalars, never
    import internally, and return NumPy arrays.
  * Public wrappers convert results to Python types and validate inputs.

Conventions (skill guidance):
  * PD, LGD are fractions in ``[0, 1]``.
  * EAD is a currency amount.
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "probability_of_default_pd_estimation",
    "loss_given_default_lgd_model",
    "exposure_at_default_ead_calculator",
    "expected_loss_el_computation",
    "unexpected_loss_ul_computation",
    "recovery_rate_estimation",
    "downturn_lgd_adjustment",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _cohort_pd(n_defaults: np.ndarray, n_obligors: np.ndarray) -> np.ndarray:
    """Per-cohort empirical default frequency.

    Args:
        n_defaults: Defaults observed in each cohort.
        n_obligors: Obligors at risk at the start of each cohort.

    Returns:
        Float64 array of per-cohort PDs (RULE 5: arrays only).
    """
    n = n_defaults.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        if n_obligors[i] > 0.0:
            out[i] = n_defaults[i] / n_obligors[i]
        else:
            out[i] = 0.0
    return out


@njit(cache=True)
def _expected_loss(pd: float, lgd: float, ead: float) -> float:
    """Single-exposure expected loss ``EL = PD * LGD * EAD``."""
    return pd * lgd * ead


@njit(cache=True)
def _unexpected_loss_vec(pd: np.ndarray, lgd: np.ndarray, ead: np.ndarray) -> np.ndarray:
    """Stand-alone unexpected loss per exposure.

    Treats default as a Bernoulli event so the loss variance for a single
    exposure is ``EAD^2 * [ LGD^2 * PD(1-PD) + PD * sigma_LGD^2 ]``. With LGD
    deterministic the stand-alone UL is ``EAD * LGD * sqrt(PD(1-PD))``.
    """
    n = pd.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        out[i] = ead[i] * lgd[i] * np.sqrt(pd[i] * (1.0 - pd[i]))
    return out


# ── Public functions ─────────────────────────────────────────────────────────


def probability_of_default_pd_estimation(
    n_defaults: np.ndarray,
    n_obligors: np.ndarray,
    floor: float = 0.0003,
) -> dict:  # type: ignore[type-arg]
    """Estimate PD from observed default cohorts (cohort / frequency method).

    Computes the per-cohort default frequency and the obligor-weighted pooled
    PD, then applies the Basel regulatory floor (3 bps for non-defaulted
    exposures under CRR Art. 160/163).

    Args:
        n_defaults: Defaults observed in each rating cohort.
        n_obligors: Obligors at risk at the start of each cohort.
        floor: Regulatory PD floor applied to the pooled estimate.

    Returns:
        Dict with ``pd_pooled`` (floored), ``pd_raw`` (unfloored), per-cohort
        ``pd_cohort`` list, and ``n_total`` obligor count.

    Raises:
        ValueError: If the inputs differ in length or are empty.
    """
    d = np.asarray(n_defaults, dtype=np.float64)
    m = np.asarray(n_obligors, dtype=np.float64)
    if d.size == 0 or d.shape != m.shape:
        raise ValueError("n_defaults and n_obligors must be non-empty and equal length")
    if np.any(m < 0.0) or np.any(d < 0.0):
        raise ValueError("counts must be non-negative")

    cohort = _cohort_pd(d, m)
    total_obligors = float(np.sum(m))
    pd_raw = float(np.sum(d) / total_obligors) if total_obligors > 0.0 else 0.0
    pd_pooled = max(pd_raw, floor)
    return {
        "pd_pooled": round(min(pd_pooled, 1.0), 10),
        "pd_raw": round(pd_raw, 10),
        "pd_cohort": [round(float(c), 10) for c in cohort],
        "n_total": int(round(total_obligors)),
        "floor": floor,
    }


def loss_given_default_lgd_model(
    recovery_amounts: np.ndarray,
    exposure_amounts: np.ndarray,
    workout_cost_rate: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Workout LGD as one minus the recovery rate, net of workout costs.

    ``LGD = 1 - (recoveries - costs) / EAD``, exposure-weighted across the
    facility sample and clipped to ``[0, 1]``.

    Args:
        recovery_amounts: Recovered amounts per defaulted facility.
        exposure_amounts: Exposure at default per facility (> 0).
        workout_cost_rate: Workout cost as a fraction of EAD (subtracted from
            recoveries).

    Returns:
        Dict with ``lgd`` (exposure-weighted), ``lgd_mean`` (simple average),
        ``recovery_rate`` and ``n_facilities``.

    Raises:
        ValueError: If inputs mismatch, are empty, or contain non-positive EAD.
    """
    rec = np.asarray(recovery_amounts, dtype=np.float64)
    ead = np.asarray(exposure_amounts, dtype=np.float64)
    if rec.size == 0 or rec.shape != ead.shape:
        raise ValueError("recovery_amounts and exposure_amounts must match and be non-empty")
    if np.any(ead <= 0.0):
        raise ValueError("exposure_amounts must be positive")
    if not 0.0 <= workout_cost_rate <= 1.0:
        raise ValueError("workout_cost_rate must be in [0, 1]")

    net_recovery = rec - workout_cost_rate * ead
    lgd_facility = np.clip(1.0 - net_recovery / ead, 0.0, 1.0)
    lgd_weighted = float(np.sum(lgd_facility * ead) / np.sum(ead))
    recovery_rate = 1.0 - lgd_weighted
    return {
        "lgd": round(lgd_weighted, 10),
        "lgd_mean": round(float(np.mean(lgd_facility)), 10),
        "recovery_rate": round(recovery_rate, 10),
        "n_facilities": int(rec.size),
    }


def exposure_at_default_ead_calculator(
    drawn: float,
    undrawn: float,
    credit_conversion_factor: float = 0.75,
) -> dict:  # type: ignore[type-arg]
    """EAD for a revolving / committed facility via the CCF method.

    ``EAD = drawn + CCF * undrawn``. The CCF (a.k.a. credit-conversion factor)
    captures the share of the currently undrawn commitment expected to be drawn
    by the time of default. Basel F-IRB uses 0.75 for unconditionally
    cancellable commitments unless otherwise specified.

    Args:
        drawn: Currently drawn (on-balance-sheet) amount.
        undrawn: Undrawn committed (off-balance-sheet) amount.
        credit_conversion_factor: CCF in ``[0, 1]`` applied to the undrawn part.

    Returns:
        Dict with ``ead``, ``drawn``, ``undrawn`` and ``ccf``.

    Raises:
        ValueError: If amounts are negative or the CCF is outside ``[0, 1]``.
    """
    if drawn < 0.0 or undrawn < 0.0:
        raise ValueError("drawn and undrawn must be non-negative")
    if not 0.0 <= credit_conversion_factor <= 1.0:
        raise ValueError("credit_conversion_factor must be in [0, 1]")

    ead = drawn + credit_conversion_factor * undrawn
    return {
        "ead": round(ead, 6),
        "drawn": round(drawn, 6),
        "undrawn": round(undrawn, 6),
        "ccf": credit_conversion_factor,
    }


def expected_loss_el_computation(
    pd: float,
    lgd: float,
    ead: float,
) -> dict:  # type: ignore[type-arg]
    """Expected Loss ``EL = PD * LGD * EAD``.

    Args:
        pd: Probability of default in ``[0, 1]``.
        lgd: Loss given default in ``[0, 1]``.
        ead: Exposure at default (currency amount, >= 0).

    Returns:
        Dict with ``el`` (currency) and ``el_rate`` (= PD * LGD, as a fraction
        of EAD).

    Raises:
        ValueError: If PD or LGD lie outside ``[0, 1]`` or EAD is negative.
    """
    if not 0.0 <= pd <= 1.0:
        raise ValueError("pd must be in [0, 1]")
    if not 0.0 <= lgd <= 1.0:
        raise ValueError("lgd must be in [0, 1]")
    if ead < 0.0:
        raise ValueError("ead must be non-negative")

    el = _expected_loss(pd, lgd, ead)
    return {
        "el": round(float(el), 6),
        "el_rate": round(pd * lgd, 10),
        "pd": pd,
        "lgd": lgd,
        "ead": ead,
    }


def unexpected_loss_ul_computation(
    pd: np.ndarray,
    lgd: np.ndarray,
    ead: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Stand-alone Unexpected Loss per exposure and the un-diversified sum.

    For a Bernoulli default with deterministic LGD, the stand-alone UL of one
    exposure is ``EAD * LGD * sqrt(PD(1-PD))`` — the loss standard deviation.
    The portfolio UL reported here is the *sum* of stand-alone ULs (i.e. the
    fully-correlated upper bound); correlation-aware UL is handled by the
    Vasicek / CreditMetrics models in :mod:`engine.credit_var`.

    Args:
        pd: Per-exposure PD array in ``[0, 1]``.
        lgd: Per-exposure LGD array in ``[0, 1]``.
        ead: Per-exposure EAD array (>= 0).

    Returns:
        Dict with per-exposure ``ul`` list, ``ul_sum`` (perfectly correlated)
        and ``ul_independent`` (root-sum-of-squares, zero correlation).

    Raises:
        ValueError: If shapes mismatch or values are out of range.
    """
    p = np.asarray(pd, dtype=np.float64)
    lgd_arr = np.asarray(lgd, dtype=np.float64)
    e = np.asarray(ead, dtype=np.float64)
    if not (p.shape == lgd_arr.shape == e.shape) or p.size == 0:
        raise ValueError("pd, lgd, ead must share the same non-empty shape")
    if np.any((p < 0.0) | (p > 1.0)) or np.any((lgd_arr < 0.0) | (lgd_arr > 1.0)):
        raise ValueError("pd and lgd must lie in [0, 1]")
    if np.any(e < 0.0):
        raise ValueError("ead must be non-negative")

    ul = _unexpected_loss_vec(p, lgd_arr, e)
    return {
        "ul": [round(float(u), 6) for u in ul],
        "ul_sum": round(float(np.sum(ul)), 6),
        "ul_independent": round(float(np.sqrt(np.sum(ul**2))), 6),
        "n_exposures": int(p.size),
    }


def recovery_rate_estimation(
    recovery_amounts: np.ndarray,
    exposure_amounts: np.ndarray,
    discount_factors: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Estimate the recovery rate (1 - LGD) from a defaulted-facility sample.

    Supports optional present-valuing of recoveries via per-facility discount
    factors (workout recoveries are received some time after default).

    Args:
        recovery_amounts: Nominal recovered amounts per facility.
        exposure_amounts: Exposure at default per facility (> 0).
        discount_factors: Optional per-facility discount factors in ``(0, 1]``
            applied to recoveries; ``None`` means no discounting.

    Returns:
        Dict with ``recovery_rate`` (exposure-weighted), ``recovery_rate_mean``,
        the implied ``lgd`` and ``n_facilities``.

    Raises:
        ValueError: If inputs mismatch, are empty, or EAD/discounts are invalid.
    """
    rec = np.asarray(recovery_amounts, dtype=np.float64)
    ead = np.asarray(exposure_amounts, dtype=np.float64)
    if rec.size == 0 or rec.shape != ead.shape:
        raise ValueError("recovery_amounts and exposure_amounts must match and be non-empty")
    if np.any(ead <= 0.0):
        raise ValueError("exposure_amounts must be positive")

    if discount_factors is None:
        df = np.ones_like(rec)
    else:
        df = np.asarray(discount_factors, dtype=np.float64)
        if df.shape != rec.shape:
            raise ValueError("discount_factors must match recovery_amounts shape")
        if np.any((df <= 0.0) | (df > 1.0)):
            raise ValueError("discount_factors must lie in (0, 1]")

    pv_recovery = rec * df
    rr_facility = np.clip(pv_recovery / ead, 0.0, 1.0)
    rr_weighted = float(np.sum(pv_recovery) / np.sum(ead))
    rr_weighted = min(max(rr_weighted, 0.0), 1.0)
    return {
        "recovery_rate": round(rr_weighted, 10),
        "recovery_rate_mean": round(float(np.mean(rr_facility)), 10),
        "lgd": round(1.0 - rr_weighted, 10),
        "n_facilities": int(rec.size),
    }


def downturn_lgd_adjustment(
    lgd_long_run: float,
    downturn_multiplier: float = 1.0,
    floor: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Basel downturn-LGD adjustment of a long-run average LGD.

    Note: uses a multiplicative downturn scaling, a deliberate departure from
    EBA/GL/2019/03's additive fallback approach — see CRR Art. 181 for the
    underlying requirement.

    CRR Art. 181 requires LGD to reflect economic-downturn conditions when these
    are more conservative than the long-run average. The supervisory-style
    additive add-on (EBA GL) is applied as
    ``LGD_downturn = LGD_LR + max(0, multiplier - 1) * (1 - LGD_LR) * 0.5`` is
    *not* used here; instead a transparent multiplicative scaling is applied and
    clipped to ``[floor, 1]`` so the result never under-states the long-run LGD.

    Args:
        lgd_long_run: Long-run average LGD in ``[0, 1]``.
        downturn_multiplier: Multiplier (>= 1) reflecting downturn severity.
        floor: Regulatory LGD floor (e.g. 0.05 for retail mortgages, CRR
            Art. 164).

    Returns:
        Dict with ``lgd_downturn`` (clipped), ``lgd_long_run`` and the applied
        ``multiplier``.

    Raises:
        ValueError: If LGD is out of range or the multiplier is below 1.
    """
    if not 0.0 <= lgd_long_run <= 1.0:
        raise ValueError("lgd_long_run must be in [0, 1]")
    if downturn_multiplier < 1.0:
        raise ValueError("downturn_multiplier must be >= 1 (downturn is more severe)")
    if not 0.0 <= floor <= 1.0:
        raise ValueError("floor must be in [0, 1]")

    lgd_dt = min(lgd_long_run * downturn_multiplier, 1.0)
    lgd_dt = max(lgd_dt, floor, lgd_long_run)
    return {
        "lgd_downturn": round(lgd_dt, 10),
        "lgd_long_run": lgd_long_run,
        "multiplier": downturn_multiplier,
        "floor": floor,
    }

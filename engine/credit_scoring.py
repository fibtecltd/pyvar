"""engine/credit_scoring.py — Credit-scoring and PD-modelling sub-domain.

Implements rating / scoring models and PD calibration: the Altman Z-score,
logistic-regression PD (Newton-Raphson MLE), a generic ML-PD calibration
(Platt scaling / isotonic-free sigmoid recalibration), through-the-cycle and
point-in-time PD adjustments, a ratings-migration matrix estimator, a retail
scorecard, a corporate weighted-factor score, a sovereign risk score and a
sector default-rate analysis.

Numba rules (CLAUDE.md §3.1): the iterative logistic solver's inner linear
algebra is small and uses NumPy in the public layer; tight scalar recursions
(score aggregation, migration counting) are JIT-compiled and return arrays.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy import stats

__all__ = [
    "altman_z_score_credit_scoring",
    "logistic_regression_pd_model",
    "machine_learning_pd_calibration",
    "through_the_cycle_pd_adjustment",
    "point_in_time_pd_estimation",
    "ratings_migration_matrix",
    "retail_scorecard_pd_model",
    "corporate_credit_scoring_model",
    "sovereign_credit_risk_assessment",
    "sector_default_rate_analysis",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _sigmoid(z: np.ndarray) -> np.ndarray:
    """Numerically stable logistic sigmoid over an array."""
    out = np.empty(z.shape[0], dtype=np.float64)
    for i in range(z.shape[0]):
        v = z[i]
        if v >= 0.0:
            out[i] = 1.0 / (1.0 + np.exp(-v))
        else:
            ev = np.exp(v)
            out[i] = ev / (1.0 + ev)
    return out


@njit(cache=True)
def _count_migrations(from_rating: np.ndarray, to_rating: np.ndarray, n_states: int) -> np.ndarray:
    """Count transitions into an ``(n_states, n_states)`` integer matrix."""
    counts = np.zeros((n_states, n_states), dtype=np.float64)
    for k in range(from_rating.shape[0]):
        counts[from_rating[k], to_rating[k]] += 1.0
    return counts


# ── Public functions ─────────────────────────────────────────────────────────


def altman_z_score_credit_scoring(
    working_capital: float,
    retained_earnings: float,
    ebit: float,
    market_value_equity: float,
    sales: float,
    total_assets: float,
    total_liabilities: float,
) -> dict:  # type: ignore[type-arg]
    """Altman (1968) Z-score for public manufacturers.

    ``Z = 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5`` with X1 = WC/TA,
    X2 = RE/TA, X3 = EBIT/TA, X4 = MV equity / total liabilities, X5 = sales/TA.
    Zones: ``Z > 2.99`` safe, ``1.81 <= Z <= 2.99`` grey, ``Z < 1.81`` distress.

    Args:
        working_capital: Working capital.
        retained_earnings: Retained earnings.
        ebit: Earnings before interest and tax.
        market_value_equity: Market value of equity.
        sales: Net sales.
        total_assets: Total assets (> 0).
        total_liabilities: Total liabilities (> 0).

    Returns:
        Dict with ``z_score``, the categorical ``zone`` and the five component
        ratios ``x1``..``x5``.

    Raises:
        ValueError: If total assets or total liabilities are non-positive.
    """
    if total_assets <= 0.0:
        raise ValueError("total_assets must be positive")
    if total_liabilities <= 0.0:
        raise ValueError("total_liabilities must be positive")

    x1 = working_capital / total_assets
    x2 = retained_earnings / total_assets
    x3 = ebit / total_assets
    x4 = market_value_equity / total_liabilities
    x5 = sales / total_assets
    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
    if z > 2.99:
        zone = "safe"
    elif z >= 1.81:
        zone = "grey"
    else:
        zone = "distress"
    return {
        "z_score": round(float(z), 6),
        "zone": zone,
        "x1": round(x1, 6),
        "x2": round(x2, 6),
        "x3": round(x3, 6),
        "x4": round(x4, 6),
        "x5": round(x5, 6),
    }


def logistic_regression_pd_model(
    features: np.ndarray,
    defaults: np.ndarray,
    max_iter: int = 100,
    tol: float = 1e-8,
    ridge: float = 1e-6,
) -> dict:  # type: ignore[type-arg]
    """Fit a logistic-regression PD model by Newton-Raphson (IRLS) MLE.

    Estimates ``PD = sigmoid(b0 + x·b)`` from a default indicator. A small ridge
    term stabilises the Hessian on separable / collinear data. An intercept is
    added automatically.

    Args:
        features: ``(n_samples, n_features)`` design matrix (no intercept col).
        defaults: ``(n_samples,)`` binary default indicator in ``{0, 1}``.
        max_iter: Maximum Newton iterations.
        tol: Convergence tolerance on the coefficient update norm.
        ridge: L2 ridge added to the Hessian diagonal for stability.

    Returns:
        Dict with ``coefficients`` (intercept first), ``fitted_pd`` list,
        ``log_likelihood``, ``n_iter`` and ``converged``.

    Raises:
        ValueError: If shapes mismatch or labels are not binary.
    """
    x = np.atleast_2d(np.asarray(features, dtype=np.float64))
    if x.shape[0] == 1 and x.shape[1] != defaults.shape[0]:
        x = x.T
    y = np.asarray(defaults, dtype=np.float64).ravel()
    if x.shape[0] != y.shape[0] or y.size == 0:
        raise ValueError("features and defaults must have matching sample count")
    if np.any((y != 0.0) & (y != 1.0)):
        raise ValueError("defaults must be binary in {0, 1}")

    n, p = x.shape
    design = np.hstack([np.ones((n, 1)), x])
    beta = np.zeros(p + 1, dtype=np.float64)
    converged = False
    n_iter = 0
    for n_iter in range(1, max_iter + 1):
        eta = design @ beta
        mu = _sigmoid(eta)
        w = np.clip(mu * (1.0 - mu), 1e-12, None)
        gradient = design.T @ (y - mu)
        hessian = design.T @ (design * w[:, None]) + ridge * np.eye(p + 1)
        step = np.linalg.solve(hessian, gradient)
        beta = beta + step
        if np.linalg.norm(step) < tol:
            converged = True
            break

    eta = design @ beta
    fitted = _sigmoid(eta)
    eps = 1e-12
    ll = float(np.sum(y * np.log(fitted + eps) + (1.0 - y) * np.log(1.0 - fitted + eps)))
    return {
        "coefficients": [round(float(b), 8) for b in beta],
        "fitted_pd": [round(float(f), 10) for f in fitted],
        "log_likelihood": round(ll, 6),
        "n_iter": int(n_iter),
        "converged": bool(converged),
    }


def machine_learning_pd_calibration(
    raw_scores: np.ndarray,
    defaults: np.ndarray,
    max_iter: int = 100,
    tol: float = 1e-8,
) -> dict:  # type: ignore[type-arg]
    """Platt-scaling calibration of raw ML scores into well-calibrated PDs.

    Many ML classifiers (gradient boosting, random forests) emit uncalibrated
    scores. Platt scaling fits a one-dimensional logistic map
    ``PD = sigmoid(a * score + b)`` so the output is a true probability. The fit
    reuses the Newton-Raphson logistic solver on the single score feature.

    Args:
        raw_scores: ``(n_samples,)`` uncalibrated model scores.
        defaults: ``(n_samples,)`` binary default indicator.
        max_iter: Maximum Newton iterations.
        tol: Convergence tolerance.

    Returns:
        Dict with ``slope`` (a), ``intercept`` (b), ``calibrated_pd`` list,
        ``brier_score`` (mean squared calibration error) and ``converged``.

    Raises:
        ValueError: If shapes mismatch or labels are not binary.
    """
    scores = np.asarray(raw_scores, dtype=np.float64).ravel()
    y = np.asarray(defaults, dtype=np.float64).ravel()
    if scores.shape != y.shape or scores.size == 0:
        raise ValueError("raw_scores and defaults must match and be non-empty")

    fit = logistic_regression_pd_model(scores.reshape(-1, 1), y, max_iter=max_iter, tol=tol)
    intercept, slope = fit["coefficients"][0], fit["coefficients"][1]
    calibrated = np.asarray(fit["fitted_pd"], dtype=np.float64)
    brier = float(np.mean((calibrated - y) ** 2))
    return {
        "slope": round(slope, 8),
        "intercept": round(intercept, 8),
        "calibrated_pd": [round(float(c), 10) for c in calibrated],
        "brier_score": round(brier, 10),
        "converged": fit["converged"],
    }


def through_the_cycle_pd_adjustment(
    pit_pd: float,
    long_run_average_pd: float,
    cyclicality: float = 0.5,
) -> dict:  # type: ignore[type-arg]
    """Convert a point-in-time PD to a through-the-cycle PD.

    TTC PDs dampen the macro cycle for stable regulatory capital. A convex blend
    in the Gaussian-score (probit) domain is used so the result stays a valid
    probability: ``score_TTC = (1-w) score_PIT + w score_LRA`` with
    ``w = cyclicality`` and ``score = N^{-1}(PD)``.

    Args:
        pit_pd: Point-in-time PD in ``(0, 1)``.
        long_run_average_pd: Long-run central-tendency PD in ``(0, 1)``.
        cyclicality: Blend weight in ``[0, 1]`` toward the long-run anchor
            (0 = pure PIT, 1 = pure TTC).

    Returns:
        Dict with ``ttc_pd``, ``pit_pd`` and ``long_run_average_pd``.

    Raises:
        ValueError: If PDs or cyclicality are out of range.
    """
    if not 0.0 < pit_pd < 1.0 or not 0.0 < long_run_average_pd < 1.0:
        raise ValueError("PDs must lie in (0, 1)")
    if not 0.0 <= cyclicality <= 1.0:
        raise ValueError("cyclicality must be in [0, 1]")

    s_pit = float(stats.norm.ppf(pit_pd))
    s_lra = float(stats.norm.ppf(long_run_average_pd))
    s_ttc = (1.0 - cyclicality) * s_pit + cyclicality * s_lra
    ttc_pd = float(stats.norm.cdf(s_ttc))
    return {
        "ttc_pd": round(ttc_pd, 12),
        "pit_pd": pit_pd,
        "long_run_average_pd": long_run_average_pd,
        "cyclicality": cyclicality,
    }


def point_in_time_pd_estimation(
    ttc_pd: float,
    macro_index: float,
    sensitivity: float = 1.0,
) -> dict:  # type: ignore[type-arg]
    """Derive a point-in-time PD from a TTC PD and a macro factor.

    Inverse of the TTC transform: shifts the probit-domain TTC score by a
    sensitivity-scaled standardised macro index ``z`` (negative ``z`` = adverse
    conditions raise the PD): ``score_PIT = N^{-1}(PD_TTC) - sensitivity * z``.

    Args:
        ttc_pd: Through-the-cycle PD in ``(0, 1)``.
        macro_index: Standardised macroeconomic index (z-score; positive = good
            conditions).
        sensitivity: Loading of the score on the macro factor (>= 0).

    Returns:
        Dict with ``pit_pd``, ``ttc_pd`` and the applied ``macro_index``.

    Raises:
        ValueError: If TTC PD is out of range or sensitivity is negative.
    """
    if not 0.0 < ttc_pd < 1.0:
        raise ValueError("ttc_pd must be in (0, 1)")
    if sensitivity < 0.0:
        raise ValueError("sensitivity must be non-negative")

    s_ttc = float(stats.norm.ppf(ttc_pd))
    s_pit = s_ttc - sensitivity * macro_index
    pit_pd = float(stats.norm.cdf(s_pit))
    return {
        "pit_pd": round(pit_pd, 12),
        "ttc_pd": ttc_pd,
        "macro_index": macro_index,
        "sensitivity": sensitivity,
    }


def ratings_migration_matrix(
    from_rating: np.ndarray,
    to_rating: np.ndarray,
    n_states: int,
) -> dict:  # type: ignore[type-arg]
    """Estimate a row-stochastic ratings-migration matrix (cohort method).

    Counts observed transitions and normalises each row to a probability
    distribution. Empty rows (no obligors observed in that state) are set to the
    identity (a self-transition), keeping the matrix row-stochastic.

    Args:
        from_rating: Integer start-of-period rating index per obligor in
            ``[0, n_states)``.
        to_rating: Integer end-of-period rating index per obligor.
        n_states: Number of rating states (including default as the last).

    Returns:
        Dict with ``matrix`` (nested list, each row sums to 1) and ``n_states``.

    Raises:
        ValueError: If indices are out of range or arrays mismatch.
    """
    f = np.asarray(from_rating, dtype=np.int64).ravel()
    t = np.asarray(to_rating, dtype=np.int64).ravel()
    if f.shape != t.shape or f.size == 0:
        raise ValueError("from_rating and to_rating must match and be non-empty")
    if n_states < 1:
        raise ValueError("n_states must be >= 1")
    if np.any((f < 0) | (f >= n_states)) or np.any((t < 0) | (t >= n_states)):
        raise ValueError("rating indices must lie in [0, n_states)")

    counts = _count_migrations(f, t, n_states)
    matrix = np.empty((n_states, n_states), dtype=np.float64)
    for i in range(n_states):
        row_sum = float(np.sum(counts[i]))
        if row_sum > 0.0:
            matrix[i] = counts[i] / row_sum
        else:
            matrix[i] = 0.0
            matrix[i, i] = 1.0
    return {
        "matrix": [
            [round(float(matrix[i, j]), 10) for j in range(n_states)] for i in range(n_states)
        ],
        "n_states": int(n_states),
    }


def retail_scorecard_pd_model(
    feature_values: np.ndarray,
    points_per_feature: np.ndarray,
    base_points: float,
    pdo: float = 50.0,
    base_score: float = 600.0,
    base_odds: float = 50.0,
) -> dict:  # type: ignore[type-arg]
    """Retail scorecard: additive points to a PD via the points-to-double-odds map.

    A scorecard sums attribute points into a score; the score relates to odds by
    ``odds = base_odds * 2^{(score - base_score)/pdo}`` (PDO = points to double
    the odds). PD = ``1 / (1 + odds)``.

    Args:
        feature_values: ``(n_features,)`` per-attribute binary/scaled indicator.
        points_per_feature: ``(n_features,)`` points assigned per attribute.
        base_points: Intercept points added to the total.
        pdo: Points to double the odds (industry default 50).
        base_score: Reference score at which odds equal ``base_odds``.
        base_odds: Good:bad odds at ``base_score`` (e.g. 50:1).

    Returns:
        Dict with ``score``, ``pd`` and the implied ``odds``.

    Raises:
        ValueError: If arrays mismatch, are empty, or pdo/base_odds invalid.
    """
    fv = np.asarray(feature_values, dtype=np.float64).ravel()
    pts = np.asarray(points_per_feature, dtype=np.float64).ravel()
    if fv.shape != pts.shape or fv.size == 0:
        raise ValueError("feature_values and points_per_feature must match and be non-empty")
    if pdo <= 0.0 or base_odds <= 0.0:
        raise ValueError("pdo and base_odds must be positive")

    score = float(base_points + np.sum(fv * pts))
    odds = base_odds * 2.0 ** ((score - base_score) / pdo)
    pd = 1.0 / (1.0 + odds)
    return {
        "score": round(score, 6),
        "pd": round(pd, 12),
        "odds": round(odds, 8),
    }


def corporate_credit_scoring_model(
    factor_scores: np.ndarray,
    factor_weights: np.ndarray,
    pd_floor: float = 0.0003,
    pd_anchor: float = 0.5,
) -> dict:  # type: ignore[type-arg]
    """Weighted-factor corporate credit score mapped to a PD.

    Combines normalised factor scores (e.g. leverage, coverage, profitability,
    each in ``[0, 1]`` with 1 = strongest) into a composite ``[0, 1]`` rating
    strength, then maps to PD via ``PD = pd_anchor * (1 - strength)`` floored at
    ``pd_floor``. A perfectly strong borrower hits the floor.

    Args:
        factor_scores: ``(k,)`` factor strengths in ``[0, 1]`` (1 = best).
        factor_weights: ``(k,)`` non-negative weights (normalised internally).
        pd_floor: Regulatory PD floor.
        pd_anchor: PD assigned to the weakest borrower (strength 0).

    Returns:
        Dict with ``composite_score`` (strength), ``pd`` and ``rating_bucket``
        (1=strong .. 5=weak).

    Raises:
        ValueError: If arrays mismatch, weights sum to zero, or scores invalid.
    """
    s = np.asarray(factor_scores, dtype=np.float64).ravel()
    w = np.asarray(factor_weights, dtype=np.float64).ravel()
    if s.shape != w.shape or s.size == 0:
        raise ValueError("factor_scores and factor_weights must match and be non-empty")
    if np.any((s < 0.0) | (s > 1.0)):
        raise ValueError("factor_scores must lie in [0, 1]")
    if np.any(w < 0.0) or np.sum(w) <= 0.0:
        raise ValueError("factor_weights must be non-negative and sum positive")

    strength = float(np.sum(s * w) / np.sum(w))
    pd = max(pd_anchor * (1.0 - strength), pd_floor)
    bucket = int(np.clip(np.ceil((1.0 - strength) * 5.0), 1, 5))
    return {
        "composite_score": round(strength, 8),
        "pd": round(pd, 12),
        "rating_bucket": bucket,
    }


def sovereign_credit_risk_assessment(
    debt_to_gdp: float,
    fiscal_balance_pct: float,
    current_account_pct: float,
    fx_reserves_months: float,
    governance_score: float,
) -> dict:  # type: ignore[type-arg]
    """Composite sovereign credit-risk score from macro-fiscal indicators.

    Maps standard sovereign indicators into a ``[0, 100]`` creditworthiness
    score (higher = stronger): high debt/GDP and twin deficits reduce the score;
    larger FX reserves and stronger governance raise it. The score is mapped to
    an indicative PD via a logistic transform.

    Args:
        debt_to_gdp: General-government debt / GDP (e.g. 0.6 = 60%).
        fiscal_balance_pct: Fiscal balance / GDP (deficit negative).
        current_account_pct: Current-account balance / GDP.
        fx_reserves_months: FX reserves in months of imports (>= 0).
        governance_score: World-Bank-style governance index in ``[0, 1]``.

    Returns:
        Dict with ``credit_score`` (0-100), ``pd`` and a ``rating`` band
        (``investment_grade`` / ``speculative`` / ``high_risk``).

    Raises:
        ValueError: If governance score is out of range or reserves negative.
    """
    if not 0.0 <= governance_score <= 1.0:
        raise ValueError("governance_score must be in [0, 1]")
    if fx_reserves_months < 0.0:
        raise ValueError("fx_reserves_months must be non-negative")

    # Indicator contributions (all expressed as positive = better).
    raw = (
        -40.0 * debt_to_gdp
        + 200.0 * fiscal_balance_pct
        + 100.0 * current_account_pct
        + 3.0 * fx_reserves_months
        + 40.0 * governance_score
    )
    score = float(np.clip(50.0 + raw, 0.0, 100.0))
    # Logistic PD: midpoint at score 50, steepness chosen for plausible spread.
    pd = float(1.0 / (1.0 + np.exp((score - 30.0) / 12.0)))
    if score >= 60.0:
        rating = "investment_grade"
    elif score >= 40.0:
        rating = "speculative"
    else:
        rating = "high_risk"
    return {
        "credit_score": round(score, 6),
        "pd": round(pd, 12),
        "rating": rating,
    }


def sector_default_rate_analysis(
    sector_defaults: np.ndarray,
    sector_obligors: np.ndarray,
    sector_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Per-sector default-rate analysis with a concentration of distress.

    Computes each sector's default rate, the obligor-weighted overall rate and
    each sector's relative risk versus the portfolio average (lift > 1 means the
    sector defaults more than average).

    Args:
        sector_defaults: Defaults observed per sector.
        sector_obligors: Obligors per sector (>= defaults).
        sector_names: Optional labels; defaults to ``sector_0, ...``.

    Returns:
        Dict with ``rates`` (name -> default rate), ``overall_rate``, ``lift``
        (name -> relative risk) and the ``riskiest_sector``.

    Raises:
        ValueError: If arrays mismatch or counts are invalid.
    """
    d = np.asarray(sector_defaults, dtype=np.float64).ravel()
    o = np.asarray(sector_obligors, dtype=np.float64).ravel()
    if d.shape != o.shape or d.size == 0:
        raise ValueError("sector_defaults and sector_obligors must match and be non-empty")
    if np.any(o <= 0.0) or np.any(d < 0.0) or np.any(d > o):
        raise ValueError("require 0 <= defaults <= obligors and obligors > 0")
    if sector_names is None:
        sector_names = [f"sector_{i}" for i in range(d.size)]

    rates = d / o
    overall = float(np.sum(d) / np.sum(o))
    lift = rates / overall if overall > 0.0 else np.zeros_like(rates)
    riskiest = sector_names[int(np.argmax(rates))]
    return {
        "rates": {sector_names[i]: round(float(rates[i]), 10) for i in range(d.size)},
        "overall_rate": round(overall, 10),
        "lift": {sector_names[i]: round(float(lift[i]), 8) for i in range(d.size)},
        "riskiest_sector": riskiest,
    }

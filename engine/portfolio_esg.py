"""engine/portfolio_esg.py — ESG, sustainability & rebalancing analytics.

Implements the ESG & Sustainability sub-domain of Portfolio Analytics:
rebalancing optimiser, ESG score integration, and carbon footprint attribution.

Numba rules (CLAUDE.md §3.1): the rebalancing trade/cost computation runs in a
JIT kernel returning a NumPy array; ESG/carbon aggregations are vectorised
NumPy in the pure-Python wrappers. SciPy is used for the constrained ESG
optimisation in the pure-Python wrapper only.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy.optimize import minimize

__all__ = [
    "rebalancing_optimiser",
    "esg_score_integration",
    "carbon_footprint_attribution",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _rebalance_trades(
    current: np.ndarray,
    target: np.ndarray,
    cost_bps: np.ndarray,
) -> np.ndarray:
    """Trade sizes and proportional transaction costs to reach the target.

    Returns a (2, n) array: row 0 trade (target - current), row 1 cost per asset
    (|trade| * cost_bps / 1e4) (RULE 5: arrays only).
    """
    n = current.shape[0]
    out = np.empty((2, n), dtype=np.float64)
    for i in range(n):
        trade = target[i] - current[i]
        out[0, i] = trade
        out[1, i] = abs(trade) * cost_bps[i] / 1.0e4
    return out


# ── Public functions ──────────────────────────────────────────────────────────


def rebalancing_optimiser(
    current_weights: np.ndarray,
    target_weights: np.ndarray,
    cost_bps: np.ndarray,
    no_trade_band: float = 0.0,
    asset_volatility: np.ndarray | None = None,
    risk_aversion: float | None = None,
) -> dict:  # type: ignore[type-arg]
    """Rebalancing optimiser with a no-trade band.

    Computes the trades to move from current to target weights, suppressing
    trades within a no-trade band to avoid churn, and reports turnover and
    total transaction cost.

    By default ``no_trade_band`` is a single user-supplied absolute weight
    threshold applied uniformly to every asset (unchanged prior behaviour).
    Supplying both ``asset_volatility`` and ``risk_aversion`` instead
    *derives* a per-asset band from the classic Constantinides (1986) /
    Davis & Norman (1990) asymptotic no-trade-region half-width — the
    closed-form cube-root result that Leland's (1999) mean-variance
    tracking-error approximation and Donohue & Yip's (2003) practitioner
    rebalancing-band heuristic both build on:

        h_i = ( (3/4) * c_i * sigma_i^2 * w_i^tgt * (1 - w_i^tgt)^2 / gamma )^(1/3)

    where ``c_i`` is the proportional transaction cost (``cost_bps_i /
    1e4``), ``sigma_i`` is asset i's return volatility, ``w_i^tgt`` is asset
    i's target weight (the frictionless-optimal allocation the band is
    centred on) and ``gamma`` is the investor's (CRRA) risk-aversion
    coefficient. The half-width widens with cost and volatility (cube-root
    scaling) and narrows as risk aversion rises — more risk-averse investors
    tolerate less drift before trading. This is the classic single-risky-
    asset asymptotic result applied per-asset; it is not a reproduction of
    Leland's or Donohue & Yip's own published numerical examples (no
    published table was available to cross-check exact figures against).

    When the derived-band mode is used, it *replaces* the scalar
    ``no_trade_band`` for that call rather than combining with it; when
    either ``asset_volatility`` or ``risk_aversion`` is omitted, behaviour
    is unchanged — the scalar ``no_trade_band`` is used exactly as before.

    Args:
        current_weights: Current portfolio weights.
        target_weights: Desired target weights.
        cost_bps: Proportional cost in basis points per asset.
        no_trade_band: Absolute weight threshold below which no trade is
            made. Ignored when the derived-band mode is active.
        asset_volatility: Optional per-asset return volatility (sigma_i).
            Supply together with ``risk_aversion`` to derive the no-trade
            band instead of using the scalar ``no_trade_band``.
        risk_aversion: Optional CRRA risk-aversion coefficient (gamma > 0).
            Supply together with ``asset_volatility`` to derive the band.

    Returns:
        Dict with ``trades`` (per asset), ``total_cost``, ``turnover`` and
        the post-trade ``new_weights``. When the derived-band mode is used,
        also includes ``derived_no_trade_band`` (per-asset list).

    Raises:
        ValueError: If the weight/cost arrays differ in length or are
            empty, if exactly one of ``asset_volatility``/``risk_aversion``
            is supplied, if ``risk_aversion`` is not positive, or if
            ``asset_volatility`` does not match the number of assets.
    """
    cur = np.asarray(current_weights, dtype=np.float64)
    tgt = np.asarray(target_weights, dtype=np.float64)
    cost = np.asarray(cost_bps, dtype=np.float64)
    n = cur.size
    if n == 0 or not (tgt.size == cost.size == n):
        raise ValueError("weight/cost arrays must be non-empty and equal length")

    use_derived_band = asset_volatility is not None or risk_aversion is not None
    if use_derived_band:
        if asset_volatility is None or risk_aversion is None:
            raise ValueError(
                "asset_volatility and risk_aversion must both be supplied together "
                "to derive the no-trade band"
            )
        if risk_aversion <= 0.0:
            raise ValueError("risk_aversion must be positive")
        vol = np.asarray(asset_volatility, dtype=np.float64)
        if vol.size != n:
            raise ValueError("asset_volatility must match the number of assets")
        cost_frac = cost / 1.0e4
        # Clip to non-negative: the closed form is derived for w in (0, 1);
        # a target weight outside that range (short/leveraged) would
        # otherwise drive the bracketed term negative.
        weight_term = np.clip(tgt * (1.0 - tgt) ** 2, 0.0, None)
        band_vec = np.cbrt(0.75 * cost_frac * vol**2 * weight_term / risk_aversion)
    else:
        band_vec = np.full(n, no_trade_band, dtype=np.float64)

    res = _rebalance_trades(cur, tgt, cost)
    trades = res[0].copy()
    # Apply the no-trade band: small drifts are not traded.
    mask = np.abs(trades) < band_vec
    trades[mask] = 0.0
    costs = np.abs(trades) * cost / 1.0e4
    new_weights = cur + trades
    out: dict = {  # type: ignore[type-arg]
        "trades": [round(float(t), 8) for t in trades],
        "new_weights": [round(float(w), 8) for w in new_weights],
        "total_cost": round(float(np.sum(costs)), 10),
        "turnover": round(0.5 * float(np.sum(np.abs(trades))), 8),
    }
    if use_derived_band:
        out["derived_no_trade_band"] = [round(float(b), 8) for b in band_vec]
    return out


def esg_score_integration(
    weights: np.ndarray,
    esg_scores: np.ndarray,
    min_esg_score: float | None = None,
    cov_matrix: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """ESG score integration — weighted score and optional ESG-constrained tilt.

    Computes the weighted-average portfolio ESG score. If ``min_esg_score`` and
    a covariance matrix are supplied, solves a minimum-variance long-only
    portfolio subject to the weighted ESG score meeting the floor.

    Args:
        weights: Current portfolio weights.
        esg_scores: ESG score per asset (higher is better).
        min_esg_score: Optional minimum weighted ESG score to enforce.
        cov_matrix: Optional covariance for the ESG-constrained re-optimisation.

    Returns:
        Dict with ``portfolio_esg_score`` and, when re-optimising,
        ``optimised_weights`` and ``optimised_esg_score``.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    w = np.asarray(weights, dtype=np.float64)
    esg = np.asarray(esg_scores, dtype=np.float64)
    n = w.size
    if n == 0 or esg.size != n:
        raise ValueError("weights and esg_scores must match and be non-empty")

    total_w = float(np.sum(w))
    port_score = float(np.sum(w * esg) / total_w) if total_w != 0.0 else 0.0
    result: dict = {"portfolio_esg_score": round(port_score, 8)}  # type: ignore[type-arg]

    if min_esg_score is not None and cov_matrix is not None:
        cov = np.asarray(cov_matrix, dtype=np.float64)
        if cov.shape != (n, n):
            raise ValueError("cov_matrix must be (n_assets, n_assets) matching weights")
        constraints = (
            {"type": "eq", "fun": lambda x: np.sum(x) - 1.0},
            {"type": "ineq", "fun": lambda x: float(x @ esg) - min_esg_score},
        )
        opt = minimize(
            lambda x: float(x @ cov @ x),
            np.full(n, 1.0 / n),
            method="SLSQP",
            bounds=[(0.0, 1.0)] * n,
            constraints=constraints,
        )
        result["optimised_weights"] = [round(float(x), 8) for x in opt.x]
        result["optimised_esg_score"] = round(float(opt.x @ esg), 8)
        result["success"] = bool(opt.success)
    return result


def carbon_footprint_attribution(
    weights: np.ndarray,
    carbon_intensities: np.ndarray,
    portfolio_value: float,
    asset_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Carbon footprint attribution (WACI and financed emissions).

    Computes the Weighted Average Carbon Intensity (WACI) and attributes the
    financed emissions to each holding by its invested value. Contributions sum
    to the total financed emissions.

    ``total_financed_emissions`` scales revenue-intensity by invested value
    per holding, which does not match the ownership-share method used by the
    TCFD/PCAF financed-emissions standards.

    Args:
        weights: Portfolio weights per holding (sum to 1).
        carbon_intensities: Carbon intensity per holding (tCO2e per $M, say).
        portfolio_value: Total portfolio value in $M consistent with intensity.
        asset_names: Optional labels; defaults to ``asset_0, ...``.

    Returns:
        Dict with ``waci``, ``total_financed_emissions``, ``contributions``
        (name -> emissions) and the ``largest_contributor``.

    Raises:
        ValueError: If the arrays differ in length or are empty.
    """
    w = np.asarray(weights, dtype=np.float64)
    ci = np.asarray(carbon_intensities, dtype=np.float64)
    n = w.size
    if n == 0 or ci.size != n:
        raise ValueError("weights and carbon_intensities must match and be non-empty")
    if asset_names is None:
        asset_names = [f"asset_{i}" for i in range(n)]

    waci = float(np.sum(w * ci))
    invested = w * portfolio_value
    emissions = invested * ci  # per-holding financed emissions
    total = float(np.sum(emissions))
    contrib = {asset_names[i]: round(float(emissions[i]), 6) for i in range(n)}
    largest = max(contrib, key=lambda k: contrib[k]) if contrib else ""
    return {
        "waci": round(waci, 8),
        "total_financed_emissions": round(total, 6),
        "contributions": contrib,
        "largest_contributor": largest,
    }

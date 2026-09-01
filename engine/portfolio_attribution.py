"""engine/portfolio_attribution.py — Performance & exposure attribution.

Implements the Performance Attribution sub-domain of Portfolio Analytics:
Brinson return attribution, factor return attribution, sector attribution,
currency attribution, GICS sector exposure, and Barra-style factor exposure.

Numba rules (CLAUDE.md §3.1): vectorised NumPy is used in the pure-Python
wrappers; the Brinson per-segment loop is a JIT kernel returning a NumPy array.
"""

from __future__ import annotations

import numpy as np
from numba import njit

__all__ = [
    "return_attribution_brinson",
    "factor_return_attribution",
    "sector_attribution",
    "currency_attribution",
    "gics_sector_exposure",
    "factor_exposure_analysis_barra",
]


# ── JIT kernels ─────────────────────────────────────────────────────────────


@njit(cache=True)
def _brinson_effects(
    wp: np.ndarray,
    wb: np.ndarray,
    rp: np.ndarray,
    rb: np.ndarray,
    total_rb: float,
) -> np.ndarray:
    """Brinson-Hood-Beebower per-segment allocation/selection/interaction.

    Returns a (3, n) array: row 0 allocation, row 1 selection, row 2
    interaction (RULE 5: arrays only). Sums reconcile to the active return.
    """
    n = wp.shape[0]
    out = np.empty((3, n), dtype=np.float64)
    for i in range(n):
        allocation = (wp[i] - wb[i]) * (rb[i] - total_rb)
        selection = wb[i] * (rp[i] - rb[i])
        interaction = (wp[i] - wb[i]) * (rp[i] - rb[i])
        out[0, i] = allocation
        out[1, i] = selection
        out[2, i] = interaction
    return out


# ── Public functions ──────────────────────────────────────────────────────────


def return_attribution_brinson(
    portfolio_weights: np.ndarray,
    benchmark_weights: np.ndarray,
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    segment_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Brinson-Hood-Beebower return attribution.

    Decomposes the active return into allocation, selection and interaction
    effects per segment. The three effects sum exactly to the total active
    return — the reconciliation property required for performance reporting.

    Args:
        portfolio_weights: Segment weights in the portfolio (sum to 1).
        benchmark_weights: Segment weights in the benchmark (sum to 1).
        portfolio_returns: Segment returns realised in the portfolio.
        benchmark_returns: Segment returns realised in the benchmark.
        segment_names: Optional labels; defaults to ``segment_0, ...``.

    Returns:
        Dict with ``allocation``, ``selection``, ``interaction`` (per segment),
        their totals, and the reconciled ``active_return``.

    Raises:
        ValueError: If the arrays differ in length or are empty.
    """
    wp = np.asarray(portfolio_weights, dtype=np.float64)
    wb = np.asarray(benchmark_weights, dtype=np.float64)
    rp = np.asarray(portfolio_returns, dtype=np.float64)
    rb = np.asarray(benchmark_returns, dtype=np.float64)
    n = wp.size
    if n == 0 or not (wb.size == rp.size == rb.size == n):
        raise ValueError("all attribution arrays must be non-empty and equal length")
    if segment_names is None:
        segment_names = [f"segment_{i}" for i in range(n)]

    total_rb = float(np.sum(wb * rb))
    eff = _brinson_effects(wp, wb, rp, rb, total_rb)
    allocation = eff[0]
    selection = eff[1]
    interaction = eff[2]
    total_rp = float(np.sum(wp * rp))
    return {
        "allocation": {segment_names[i]: round(float(allocation[i]), 10) for i in range(n)},
        "selection": {segment_names[i]: round(float(selection[i]), 10) for i in range(n)},
        "interaction": {segment_names[i]: round(float(interaction[i]), 10) for i in range(n)},
        "total_allocation": round(float(np.sum(allocation)), 10),
        "total_selection": round(float(np.sum(selection)), 10),
        "total_interaction": round(float(np.sum(interaction)), 10),
        "active_return": round(total_rp - total_rb, 10),
    }


def factor_return_attribution(
    factor_exposures: np.ndarray,
    factor_returns: np.ndarray,
    specific_return: float,
    factor_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Factor return attribution.

    Decomposes the realised portfolio return into per-factor contributions
    ``exposure_i * factor_return_i`` plus a specific (idiosyncratic) component.

    Args:
        factor_exposures: Portfolio exposure (beta) to each factor.
        factor_returns: Realised return of each factor over the period.
        specific_return: Idiosyncratic return not explained by factors.
        factor_names: Optional labels; defaults to ``factor_0, ...``.

    Returns:
        Dict with ``contributions`` (name -> return), ``factor_total``,
        ``specific_return`` and the reconciled ``total_return``.

    Raises:
        ValueError: If exposures and returns differ in length or are empty.
    """
    b = np.asarray(factor_exposures, dtype=np.float64)
    fr = np.asarray(factor_returns, dtype=np.float64)
    n = b.size
    if n == 0 or fr.size != n:
        raise ValueError("factor_exposures and factor_returns must match and be non-empty")
    if factor_names is None:
        factor_names = [f"factor_{i}" for i in range(n)]

    contrib = b * fr
    factor_total = float(np.sum(contrib))
    return {
        "contributions": {factor_names[i]: round(float(contrib[i]), 10) for i in range(n)},
        "factor_total": round(factor_total, 10),
        "specific_return": round(float(specific_return), 10),
        "total_return": round(factor_total + float(specific_return), 10),
    }


def sector_attribution(
    portfolio_weights: np.ndarray,
    benchmark_weights: np.ndarray,
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    sector_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Sector attribution — Brinson allocation/selection grouped by sector.

    A thin specialisation of :func:`return_attribution_brinson` where segments
    are GICS sectors. Allocation+selection+interaction reconcile to the active
    return.

    Args:
        portfolio_weights: Portfolio sector weights (sum to 1).
        benchmark_weights: Benchmark sector weights (sum to 1).
        portfolio_returns: Portfolio sector returns.
        benchmark_returns: Benchmark sector returns.
        sector_names: Optional sector labels.

    Returns:
        Dict identical in structure to :func:`return_attribution_brinson` with
        an added per-sector ``total_effect``.

    Raises:
        ValueError: If the arrays differ in length or are empty.
    """
    base = return_attribution_brinson(
        portfolio_weights,
        benchmark_weights,
        portfolio_returns,
        benchmark_returns,
        sector_names,
    )
    keys = list(base["allocation"].keys())
    base["total_effect"] = {
        k: round(base["allocation"][k] + base["selection"][k] + base["interaction"][k], 10)
        for k in keys
    }
    return base


def currency_attribution(
    local_returns: np.ndarray,
    fx_returns: np.ndarray,
    weights: np.ndarray,
    currency_names: list[str] | None = None,
    local_risk_free: np.ndarray | None = None,
    base_risk_free: float | None = None,
) -> dict:  # type: ignore[type-arg]
    """Currency attribution -- naive geometric split, or genuine Karnosky-Singer.

    By default (``local_risk_free``/``base_risk_free`` omitted, unchanged
    prior behaviour) this splits the base-currency return into a
    local-market component and a currency (FX) component per holding,
    weighted by exposure, via the geometric identity
    ``base = (1+local)(1+fx)-1`` with currency as the residual. This naive
    split is NOT Karnosky-Singer -- see Bacon, C. (2008), "Practical
    Portfolio Performance Measurement and Attribution", 2nd ed., Ch. 6,
    which presents it as the baseline before introducing Karnosky-Singer.

    Supplying BOTH ``local_risk_free`` (per-holding local-currency
    risk-free/cash rate) and ``base_risk_free`` (the reporting/base
    currency's own risk-free rate) switches to Karnosky & Singer's (1994)
    genuine decomposition ("The Currency Dimension of Global Asset
    Management and Performance Attribution", CFA Institute Research
    Foundation): local returns are first netted against the *local*
    risk-free rate into a local return PREMIUM (the market-selection
    component the currency side must not re-capture), and the currency
    side is split into the base cash return and a currency SURPRISE --
    the currency return net of the covered-interest-parity forward
    premium implied by the two risk-free rates -- rather than absorbing
    the interest-rate differential as an unexplained residual:

        premium_i = (1+local_i)/(1+local_rf_i) - 1
        forward_premium_i = (1+base_rf)/(1+local_rf_i) - 1   (covered interest parity)
        surprise_i = (1+fx_i)/(1+forward_premium_i) - 1

    These combine via the exact geometric identity
    ``(1+base_rf)(1+premium_i)(1+surprise_i) = (1+local_i)(1+fx_i)`` -- i.e.
    Karnosky-Singer re-partitions the *same* total base-currency return
    used by the naive split, it does not change it (verified in tests).
    The ``currency_effect`` bucket is further broken into
    ``base_cash_effect`` (``base_rf``, common to every holding),
    ``currency_surprise_effect`` (``surprise_i``) and a small
    ``currency_interaction_effect`` residual capturing the compounding
    cross-terms between the three multiplicative legs -- the same
    reconciling-residual pattern :func:`return_attribution_brinson` uses
    for its own interaction effect, so the three currency sub-effects sum
    exactly to ``currency_effect`` (which itself sums with ``local_effect``
    to ``total_return``, as before).

    Args:
        local_returns: Local-currency return per holding.
        fx_returns: Currency (FX) return per holding (base vs local).
        weights: Portfolio weight per holding (sum to 1).
        currency_names: Optional labels; defaults to ``ccy_0, ...``.
        local_risk_free: Optional per-holding local-currency risk-free
            rate. Supply together with ``base_risk_free`` to switch to the
            Karnosky-Singer decomposition.
        base_risk_free: Optional reporting/base-currency risk-free rate
            (a single rate, common to every holding). Supply together with
            ``local_risk_free`` to switch to the Karnosky-Singer
            decomposition.

    Returns:
        Dict with ``local_effect``, ``currency_effect`` (per holding),
        ``total_local``, ``total_currency`` and the reconciled
        ``total_return``. When the Karnosky-Singer mode is used, also
        includes per-holding ``base_cash_effect``, ``currency_surprise_effect``
        and ``currency_interaction_effect`` (summing exactly to
        ``currency_effect``), plus their totals.

    Raises:
        ValueError: If the arrays differ in length or are empty, or if
            exactly one of ``local_risk_free``/``base_risk_free`` is
            supplied, or ``local_risk_free`` does not match the number of
            holdings.
    """
    lr = np.asarray(local_returns, dtype=np.float64)
    fx = np.asarray(fx_returns, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    n = lr.size
    if n == 0 or not (fx.size == w.size == n):
        raise ValueError("all currency attribution arrays must match and be non-empty")
    if currency_names is None:
        currency_names = [f"ccy_{i}" for i in range(n)]

    # Exact geometric base-currency return -- identical in both modes, so
    # Karnosky-Singer re-partitions this total rather than changing it.
    base_ret = (1.0 + lr) * (1.0 + fx) - 1.0

    use_karnosky_singer = local_risk_free is not None or base_risk_free is not None
    if use_karnosky_singer:
        if local_risk_free is None or base_risk_free is None:
            raise ValueError(
                "local_risk_free and base_risk_free must both be supplied together "
                "to use the Karnosky-Singer decomposition"
            )
        rf_local = np.asarray(local_risk_free, dtype=np.float64)
        if rf_local.size != n:
            raise ValueError("local_risk_free must match the number of holdings")

        premium = (1.0 + lr) / (1.0 + rf_local) - 1.0
        forward_premium = (1.0 + base_risk_free) / (1.0 + rf_local) - 1.0
        surprise = (1.0 + fx) / (1.0 + forward_premium) - 1.0

        local_effect = w * premium
        currency_effect = w * (base_ret - premium)
        base_cash_effect = w * base_risk_free
        currency_surprise_effect = w * surprise
        currency_interaction_effect = currency_effect - base_cash_effect - currency_surprise_effect
    else:
        local_effect = w * lr
        currency_effect = w * (base_ret - lr)

    total_local = float(np.sum(local_effect))
    total_currency = float(np.sum(currency_effect))
    out: dict = {  # type: ignore[type-arg]
        "local_effect": {currency_names[i]: round(float(local_effect[i]), 10) for i in range(n)},
        "currency_effect": {
            currency_names[i]: round(float(currency_effect[i]), 10) for i in range(n)
        },
        "total_local": round(total_local, 10),
        "total_currency": round(total_currency, 10),
        "total_return": round(total_local + total_currency, 10),
    }
    if use_karnosky_singer:
        out["base_cash_effect"] = {
            currency_names[i]: round(float(base_cash_effect[i]), 10) for i in range(n)
        }
        out["currency_surprise_effect"] = {
            currency_names[i]: round(float(currency_surprise_effect[i]), 10) for i in range(n)
        }
        out["currency_interaction_effect"] = {
            currency_names[i]: round(float(currency_interaction_effect[i]), 10) for i in range(n)
        }
        out["total_base_cash"] = round(float(np.sum(base_cash_effect)), 10)
        out["total_currency_surprise"] = round(float(np.sum(currency_surprise_effect)), 10)
        out["total_currency_interaction"] = round(float(np.sum(currency_interaction_effect)), 10)
    return out


def gics_sector_exposure(
    weights: np.ndarray,
    sector_codes: list[str],
) -> dict:  # type: ignore[type-arg]
    """GICS sector exposure aggregation.

    Aggregates position weights into GICS sector buckets and reports each
    sector's share of the portfolio. Shares sum to the total invested weight.

    Args:
        weights: Position weights per holding.
        sector_codes: GICS sector label per holding (same ordering).

    Returns:
        Dict with ``sector_exposure`` (sector -> weight), ``n_sectors`` and the
        ``largest_sector``.

    Raises:
        ValueError: If lengths differ or are empty.
    """
    w = np.asarray(weights, dtype=np.float64)
    if w.size == 0 or len(sector_codes) != w.size:
        raise ValueError("weights and sector_codes must match and be non-empty")

    exposure: dict[str, float] = {}
    for i in range(w.size):
        exposure[sector_codes[i]] = exposure.get(sector_codes[i], 0.0) + float(w[i])
    rounded = {k: round(v, 8) for k, v in exposure.items()}
    largest = max(rounded, key=lambda k: rounded[k]) if rounded else ""
    return {
        "sector_exposure": rounded,
        "n_sectors": len(rounded),
        "largest_sector": largest,
    }


def factor_exposure_analysis_barra(
    asset_exposures: np.ndarray,
    weights: np.ndarray,
    factor_names: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Barra-style portfolio factor exposure.

    Aggregates per-asset factor loadings into portfolio-level exposures
    ``Bᵀ w`` — the active/absolute factor tilts of the portfolio.

    Args:
        asset_exposures: (n_assets, n_factors) factor loading matrix.
        weights: Portfolio weight per asset.
        factor_names: Optional labels; defaults to ``factor_0, ...``.

    Returns:
        Dict with ``factor_exposures`` (name -> exposure) and the
        ``dominant_factor`` by absolute exposure.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    b = np.atleast_2d(np.asarray(asset_exposures, dtype=np.float64))
    w = np.asarray(weights, dtype=np.float64)
    if b.shape[0] != w.size:
        raise ValueError("asset_exposures rows must match weights length")
    k = b.shape[1]
    if factor_names is None:
        factor_names = [f"factor_{i}" for i in range(k)]

    exposures = b.T @ w
    exp_map = {factor_names[i]: round(float(exposures[i]), 8) for i in range(k)}
    dominant = max(exp_map, key=lambda f: abs(exp_map[f])) if exp_map else ""
    return {
        "factor_exposures": exp_map,
        "dominant_factor": dominant,
    }

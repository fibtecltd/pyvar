"""engine/alm_nii_eve.py — NII & EVE simulation (ALM & Balance Sheet).

Stressed net-interest-income projection, Economic Value of Equity (EVE), EVE
sensitivity to the six IRRBB shocks and liquidity-adjusted NII.

[REGULATORY] EVE is the present value of asset cashflows minus the present value
of liability cashflows (BCBS d368). ΔEVE under a shock is the change in this
net present value — never a simple duration approximation when full cashflows
are available.

Pure-Python vectorised NumPy wrappers (CLAUDE.md §3.1 satisfied trivially).
"""

from __future__ import annotations

import numpy as np

from engine.alm_irrbb import irrbb_six_standard_rate_shocks

__all__ = [
    "nii_simulation_stress",
    "economic_value_of_equity_eve",
    "eve_sensitivity_analysis",
    "liquidity_adjusted_nii",
]


def nii_simulation_stress(
    asset_balances: np.ndarray,
    asset_rates: np.ndarray,
    liability_balances: np.ndarray,
    liability_rates: np.ndarray,
    rate_shock: float,
    asset_beta: float = 1.0,
    liability_beta: float = 0.5,
) -> dict:  # type: ignore[type-arg]
    """Stressed NII under a parallel rate shock with repricing betas.

    Asset and liability rates reprice by ``beta · shock`` (betas capture
    incomplete pass-through, especially on deposits). Returns the stressed NII
    and the change versus baseline.

    Args:
        asset_balances: Balance per asset bucket (currency).
        asset_rates: Base yield per asset bucket (decimal).
        liability_balances: Balance per liability bucket.
        liability_rates: Base cost per liability bucket (decimal).
        rate_shock: Parallel rate shock (decimal).
        asset_beta: Asset repricing beta in [0, 1+].
        liability_beta: Liability (deposit) repricing beta in [0, 1+].

    Returns:
        Dict with ``stressed_nii``, ``baseline_nii``, ``delta_nii``.

    Raises:
        ValueError: If paired arrays differ in length.
    """
    ab = np.asarray(asset_balances, dtype=np.float64)
    ar = np.asarray(asset_rates, dtype=np.float64)
    lb = np.asarray(liability_balances, dtype=np.float64)
    lr = np.asarray(liability_rates, dtype=np.float64)
    if ab.size != ar.size or lb.size != lr.size:
        raise ValueError("balances and rates must match length within each side")

    baseline = float(np.sum(ab * ar) - np.sum(lb * lr))
    stressed = float(
        np.sum(ab * (ar + asset_beta * rate_shock))
        - np.sum(lb * (lr + liability_beta * rate_shock))
    )
    return {
        "stressed_nii": round(stressed, 6),
        "baseline_nii": round(baseline, 6),
        "delta_nii": round(stressed - baseline, 6),
    }


def economic_value_of_equity_eve(
    asset_cashflows: np.ndarray,
    asset_times: np.ndarray,
    liability_cashflows: np.ndarray,
    liability_times: np.ndarray,
    asset_rates: np.ndarray,
    liability_rates: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Economic Value of Equity: PV(assets) − PV(liabilities).

    [REGULATORY] BCBS d368. EVE is the residual economic value accruing to
    equity holders after discounting all banking-book cashflows.

    Args:
        asset_cashflows: Asset cashflow per bucket.
        asset_times: Asset cashflow time per bucket (years).
        liability_cashflows: Liability cashflow per bucket.
        liability_times: Liability cashflow time per bucket (years).
        asset_rates: Discount zero rate per asset bucket (decimal).
        liability_rates: Discount zero rate per liability bucket (decimal).

    Returns:
        Dict with ``eve``, ``pv_assets``, ``pv_liabilities``.

    Raises:
        ValueError: If paired arrays differ in length.
    """
    ac = np.asarray(asset_cashflows, dtype=np.float64)
    at = np.asarray(asset_times, dtype=np.float64)
    ar = np.asarray(asset_rates, dtype=np.float64)
    lc = np.asarray(liability_cashflows, dtype=np.float64)
    lt = np.asarray(liability_times, dtype=np.float64)
    lr = np.asarray(liability_rates, dtype=np.float64)
    if not (ac.size == at.size == ar.size):
        raise ValueError("asset arrays must match length")
    if not (lc.size == lt.size == lr.size):
        raise ValueError("liability arrays must match length")

    pv_a = float(np.sum(ac * np.exp(-ar * at)))
    pv_l = float(np.sum(lc * np.exp(-lr * lt)))
    return {
        "eve": round(pv_a - pv_l, 6),
        "pv_assets": round(pv_a, 6),
        "pv_liabilities": round(pv_l, 6),
    }


def eve_sensitivity_analysis(
    net_cashflows: np.ndarray,
    times: np.ndarray,
    base_rates: np.ndarray,
    parallel_bps: float = 200.0,
    short_bps: float = 300.0,
    long_bps: float = 150.0,
) -> dict:  # type: ignore[type-arg]
    """EVE sensitivity (ΔEVE) under each of the six IRRBB rate shocks.

    [REGULATORY] BCBS d368. Reports ΔEVE for every prescribed scenario and the
    worst case — the headline supervisory metric.

    Args:
        net_cashflows: Net (asset − liability) cashflow per bucket.
        times: Bucket times in years.
        base_rates: Base zero rate per bucket (decimal).
        parallel_bps: Parallel shock (bps).
        short_bps: Short shock (bps).
        long_bps: Long shock (bps).

    Returns:
        Dict with ``base_eve``, per-scenario ``delta_eve`` and ``worst_case``.

    Raises:
        ValueError: If array lengths are inconsistent.
    """
    cf = np.asarray(net_cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    r0 = np.asarray(base_rates, dtype=np.float64)
    if not (cf.size == t.size == r0.size):
        raise ValueError("net_cashflows, times, base_rates must match length")

    base_eve = float(np.sum(cf * np.exp(-r0 * t)))
    shocks = irrbb_six_standard_rate_shocks(t, parallel_bps, short_bps, long_bps)
    deltas: dict[str, float] = {}
    for name, shock in shocks.items():
        shocked = r0 + np.asarray(shock, dtype=np.float64)
        deltas[name] = round(float(np.sum(cf * np.exp(-shocked * t))) - base_eve, 6)
    worst = min(deltas.values())
    return {
        "base_eve": round(base_eve, 6),
        "delta_eve": deltas,
        "worst_case": round(worst, 6),
    }


def liquidity_adjusted_nii(
    base_nii: float,
    liquidity_buffer: float,
    buffer_yield: float,
    funding_cost: float,
    liquidity_premium: float,
) -> dict:  # type: ignore[type-arg]
    """Liquidity-adjusted NII: base NII net of the liquidity-buffer carry cost.

    Holding a high-quality liquid-asset buffer earns ``buffer_yield`` but is
    funded at ``funding_cost`` plus a ``liquidity_premium`` — usually a net
    drag. Adjusted NII = base + buffer·(yield − funding − premium).

    Args:
        base_nii: Baseline net interest income (currency).
        liquidity_buffer: Size of the liquidity buffer (currency).
        buffer_yield: Yield on the buffer (decimal).
        funding_cost: Funding cost of the buffer (decimal).
        liquidity_premium: Additional liquidity premium charged (decimal).

    Returns:
        Dict with ``adjusted_nii`` and ``buffer_carry``.

    Raises:
        ValueError: If ``liquidity_buffer`` is negative.
    """
    if liquidity_buffer < 0:
        raise ValueError("liquidity_buffer must be >= 0")
    carry = liquidity_buffer * (buffer_yield - funding_cost - liquidity_premium)
    return {
        "adjusted_nii": round(float(base_nii + carry), 6),
        "buffer_carry": round(float(carry), 6),
    }

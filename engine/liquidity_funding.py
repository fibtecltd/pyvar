"""engine/liquidity_funding.py — funding risk and pricing analytics.

Covers the funding-risk sub-domain: buffer sizing, contingency-funding-plan
triggers, concentration, deposit run-off, secured-funding rollover, asset
encumbrance, collateral availability, repo stress haircuts, FX liquidity,
intragroup flows, funding cost, and liquidity transfer pricing (LTP).

These are aggregation / typed-Python wrappers (no heavy array math) per the
CLAUDE.md §3.1 guidance, with NumPy used for vectorised sums and concentration
measures.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "liquidity_buffer_sizing",
    "contingency_funding_plan_trigger",
    "wholesale_funding_concentration",
    "retail_deposit_runoff_rate",
    "secured_funding_rollover_risk",
    "asset_encumbrance_ratio",
    "collateral_availability_analysis",
    "repo_market_stress_haircut",
    "fx_liquidity_risk_by_currency",
    "intragroup_liquidity_flow",
    "funding_cost_analysis",
    "liquidity_transfer_pricing",
]


def liquidity_buffer_sizing(
    stressed_net_outflows: np.ndarray,
    confidence_buffer: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Size the liquidity buffer to the peak cumulative stressed outflow.

    The required buffer equals the maximum cumulative net outflow over the
    stress horizon (the deepest point of the cash-flow trough), optionally
    uplifted by a management ``confidence_buffer`` margin.

    Args:
        stressed_net_outflows: Per-period stressed net outflows (positive =
            drain).
        confidence_buffer: Fractional management uplift (e.g. 0.10 for +10%).

    Returns:
        Dict with ``required_buffer``, ``peak_cumulative_outflow`` and the
        ``peak_period`` index.

    Raises:
        ValueError: If the outflow array is empty or the buffer is negative.
    """
    outflows = np.asarray(stressed_net_outflows, dtype=np.float64)
    if outflows.size == 0:
        raise ValueError("stressed_net_outflows must be non-empty")
    if confidence_buffer < 0.0:
        raise ValueError("confidence_buffer must be non-negative")

    cumulative = np.cumsum(outflows)
    peak_period = int(np.argmax(cumulative))
    peak = float(cumulative[peak_period])
    peak = max(peak, 0.0)
    required = peak * (1.0 + confidence_buffer)
    return {
        "required_buffer": round(required, 2),
        "peak_cumulative_outflow": round(peak, 2),
        "peak_period": peak_period,
    }


def contingency_funding_plan_trigger(
    metrics: dict,  # type: ignore[type-arg]
    thresholds: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """Evaluate Contingency Funding Plan (CFP) activation triggers.

    Compares current early-warning metrics against their activation thresholds.
    A metric breaches when its value falls *below* the threshold (lower = worse;
    e.g. LCR, survival days). Returns the list of breached triggers and the CFP
    activation decision.

    Args:
        metrics: Mapping ``name -> current value``.
        thresholds: Mapping ``name -> minimum acceptable value``.

    Returns:
        Dict with ``breached`` (list of names), ``num_breached`` and
        ``cfp_activated`` (any breach).

    Raises:
        ValueError: If ``thresholds`` is empty.
    """
    if not thresholds:
        raise ValueError("thresholds must be non-empty")
    breached = [name for name, thr in thresholds.items() if metrics.get(name, np.inf) < thr]
    return {
        "breached": breached,
        "num_breached": len(breached),
        "cfp_activated": bool(breached),
    }


def wholesale_funding_concentration(
    counterparty_amounts: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Wholesale funding concentration via the Herfindahl-Hirschman Index.

    Computes the HHI of funding shares across counterparties (sum of squared
    shares, in [1/n, 1]) plus the largest single-counterparty share. Higher HHI
    means more concentrated, less diversified funding.

    Args:
        counterparty_amounts: Funding amount from each wholesale counterparty.

    Returns:
        Dict with ``hhi``, ``top1_share``, ``top5_share`` and
        ``effective_counterparties`` (1/HHI).

    Raises:
        ValueError: If the array is empty or total funding is zero.
    """
    amounts = np.asarray(counterparty_amounts, dtype=np.float64)
    if amounts.size == 0:
        raise ValueError("counterparty_amounts must be non-empty")
    total = float(np.sum(amounts))
    if total <= 0.0:
        raise ValueError("total wholesale funding must be positive")

    shares = amounts / total
    hhi = float(np.sum(shares**2))
    sorted_shares = np.sort(shares)[::-1]
    top1 = float(sorted_shares[0])
    top5 = float(np.sum(sorted_shares[:5]))
    return {
        "hhi": round(hhi, 6),
        "top1_share": round(top1, 6),
        "top5_share": round(top5, 6),
        "effective_counterparties": round(1.0 / hhi, 4),
    }


def retail_deposit_runoff_rate(
    deposit_balances: np.ndarray,
    runoff_rates: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Aggregate retail deposit run-off (Basel LCR categories).

    Computes the blended run-off rate across retail deposit categories (e.g.
    stable 5%, less-stable 10%, non-operational higher) and the total expected
    30-day run-off amount.

    Args:
        deposit_balances: Balance per retail deposit category.
        runoff_rates: Run-off rate per category, each in [0, 1].

    Returns:
        Dict with ``total_runoff``, ``blended_rate`` and per-category
        ``runoff_amounts``.

    Raises:
        ValueError: If lengths differ or rates lie outside [0, 1].
    """
    bal = np.asarray(deposit_balances, dtype=np.float64)
    rates = np.asarray(runoff_rates, dtype=np.float64)
    if bal.shape != rates.shape:
        raise ValueError("deposit_balances and runoff_rates must have equal length")
    if np.any(rates < 0.0) or np.any(rates > 1.0):
        raise ValueError("runoff_rates must lie in [0, 1]")
    total_bal = float(np.sum(bal))
    amounts = bal * rates
    total_runoff = float(np.sum(amounts))
    blended = total_runoff / total_bal if total_bal > 0 else 0.0
    return {
        "total_runoff": round(total_runoff, 2),
        "blended_rate": round(blended, 6),
        "runoff_amounts": [round(float(a), 2) for a in amounts],
    }


def secured_funding_rollover_risk(
    maturing_amounts: np.ndarray,
    rollover_rates: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Secured funding (repo) rollover risk.

    Estimates the funding gap from secured transactions that fail to roll: the
    non-rolled portion of each maturing tranche must be replaced or repaid.

    Args:
        maturing_amounts: Amount of secured funding maturing per tranche.
        rollover_rates: Assumed rollover (renewal) rate per tranche, in [0, 1].

    Returns:
        Dict with ``rollover_gap`` (total non-rolled), ``rolled_amount`` and the
        aggregate ``effective_rollover_rate``.

    Raises:
        ValueError: If lengths differ or rates lie outside [0, 1].
    """
    maturing = np.asarray(maturing_amounts, dtype=np.float64)
    rates = np.asarray(rollover_rates, dtype=np.float64)
    if maturing.shape != rates.shape:
        raise ValueError("maturing_amounts and rollover_rates must have equal length")
    if np.any(rates < 0.0) or np.any(rates > 1.0):
        raise ValueError("rollover_rates must lie in [0, 1]")
    total = float(np.sum(maturing))
    rolled = float(np.sum(maturing * rates))
    gap = total - rolled
    eff = rolled / total if total > 0 else 0.0
    return {
        "rollover_gap": round(gap, 2),
        "rolled_amount": round(rolled, 2),
        "effective_rollover_rate": round(eff, 6),
    }


def asset_encumbrance_ratio(
    encumbered_assets: float,
    total_assets: float,
) -> dict:  # type: ignore[type-arg]
    """Asset encumbrance ratio (EBA reporting).

    ``encumbrance = encumbered assets / total assets``. High encumbrance reduces
    the unencumbered asset pool available to monetise in stress.

    Args:
        encumbered_assets: Carrying value of encumbered assets.
        total_assets: Total assets (encumbered + unencumbered).

    Returns:
        Dict with ``encumbrance_ratio``, ``unencumbered_assets`` and
        ``unencumbered_ratio``.

    Raises:
        ValueError: If inputs are negative, total is zero, or encumbered exceeds
            total.
    """
    if encumbered_assets < 0 or total_assets <= 0:
        raise ValueError("total_assets must be positive and encumbered non-negative")
    if encumbered_assets > total_assets:
        raise ValueError("encumbered_assets cannot exceed total_assets")
    ratio = encumbered_assets / total_assets
    return {
        "encumbrance_ratio": round(float(ratio), 6),
        "unencumbered_assets": round(float(total_assets - encumbered_assets), 2),
        "unencumbered_ratio": round(float(1.0 - ratio), 6),
    }


def collateral_availability_analysis(
    collateral_values: np.ndarray,
    haircuts: np.ndarray,
    already_pledged: np.ndarray | None = None,
) -> dict:  # type: ignore[type-arg]
    """Collateral availability — post-haircut monetisable value.

    Computes the net realisable collateral value after haircuts and netting off
    already-pledged amounts — the counterbalancing capacity available to raise
    secured funding.

    Args:
        collateral_values: Market value of each collateral asset.
        haircuts: Haircut per asset, each in [0, 1].
        already_pledged: Optional pledged amount per asset to net off.

    Returns:
        Dict with ``available_collateral`` (post-haircut, net of pledged) and the
        per-asset ``post_haircut_values``.

    Raises:
        ValueError: If lengths differ or haircuts lie outside [0, 1].
    """
    values = np.asarray(collateral_values, dtype=np.float64)
    hc = np.asarray(haircuts, dtype=np.float64)
    if values.shape != hc.shape:
        raise ValueError("collateral_values and haircuts must have equal length")
    if np.any(hc < 0.0) or np.any(hc > 1.0):
        raise ValueError("haircuts must lie in [0, 1]")
    pledged = (
        np.zeros_like(values)
        if already_pledged is None
        else np.asarray(already_pledged, dtype=np.float64)
    )
    if pledged.shape != values.shape:
        raise ValueError("already_pledged must match collateral_values length")

    post_haircut = values * (1.0 - hc)
    available = np.maximum(post_haircut - pledged, 0.0)
    return {
        "available_collateral": round(float(np.sum(available)), 2),
        "post_haircut_values": [round(float(p), 2) for p in post_haircut],
    }


def repo_market_stress_haircut(
    base_haircuts: np.ndarray,
    stress_multipliers: np.ndarray,
    collateral_values: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Repo market stress — incremental margin call from widened haircuts.

    Under stress, repo haircuts widen by a multiplier. The incremental margin
    requirement is the extra collateral (or cash) the institution must post to
    maintain the same secured borrowing.

    Args:
        base_haircuts: Current repo haircut per collateral type, in [0, 1].
        stress_multipliers: Multiplier applied to each haircut under stress
            (>= 1.0).
        collateral_values: Market value of pledged collateral per type.

    Returns:
        Dict with ``stressed_haircuts`` (capped at 1.0), ``additional_margin``
        (total) and per-type ``margin_calls``.

    Raises:
        ValueError: If lengths differ, base haircuts are out of range, or
            multipliers are below 1.
    """
    base = np.asarray(base_haircuts, dtype=np.float64)
    mult = np.asarray(stress_multipliers, dtype=np.float64)
    values = np.asarray(collateral_values, dtype=np.float64)
    if not (base.shape == mult.shape == values.shape):
        raise ValueError("all arrays must have equal length")
    if np.any(base < 0.0) or np.any(base > 1.0):
        raise ValueError("base_haircuts must lie in [0, 1]")
    if np.any(mult < 1.0):
        raise ValueError("stress_multipliers must be >= 1.0")

    stressed = np.minimum(base * mult, 1.0)
    margin_calls = values * (stressed - base)
    return {
        "stressed_haircuts": [round(float(s), 6) for s in stressed],
        "additional_margin": round(float(np.sum(margin_calls)), 2),
        "margin_calls": [round(float(m), 2) for m in margin_calls],
    }


def fx_liquidity_risk_by_currency(
    inflows_by_ccy: dict,  # type: ignore[type-arg]
    outflows_by_ccy: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """FX liquidity risk — net position per significant currency.

    Computes the net liquidity gap in each currency (inflows - outflows). A
    significant negative position signals reliance on FX swap markets to fund
    the shortfall — a key vulnerability if swap markets seize.

    Args:
        inflows_by_ccy: Mapping ``currency -> inflow amount``.
        outflows_by_ccy: Mapping ``currency -> outflow amount``.

    Returns:
        Dict with ``net_by_ccy`` (currency -> net gap) and ``largest_short_ccy``
        (the currency with the most negative gap, or ``None``).

    Raises:
        ValueError: If both mappings are empty.
    """
    if not inflows_by_ccy and not outflows_by_ccy:
        raise ValueError("at least one currency mapping must be non-empty")
    currencies = set(inflows_by_ccy) | set(outflows_by_ccy)
    net = {
        ccy: round(float(inflows_by_ccy.get(ccy, 0.0) - outflows_by_ccy.get(ccy, 0.0)), 2)
        for ccy in currencies
    }
    largest_short = None
    worst = 0.0
    for ccy, val in net.items():
        if val < worst:
            worst = val
            largest_short = ccy
    return {
        "net_by_ccy": net,
        "largest_short_ccy": largest_short,
        "largest_short_amount": round(worst, 2),
    }


def intragroup_liquidity_flow(
    entity_positions: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """Intragroup liquidity flow netting.

    Nets bilateral liquidity positions across group entities to derive each
    entity's net provider/receiver status and the total internal liquidity
    transferred. Positive = net provider of liquidity to the group.

    Args:
        entity_positions: Mapping ``entity -> net position`` (provided minus
            received).

    Returns:
        Dict with ``net_providers``, ``net_receivers``, ``total_provided`` and a
        ``balanced`` flag (sums to ~0).

    Raises:
        ValueError: If ``entity_positions`` is empty.
    """
    if not entity_positions:
        raise ValueError("entity_positions must be non-empty")
    providers = {e: v for e, v in entity_positions.items() if v > 0}
    receivers = {e: v for e, v in entity_positions.items() if v < 0}
    total_provided = float(sum(providers.values()))
    net_sum = float(sum(entity_positions.values()))
    return {
        "net_providers": {e: round(float(v), 2) for e, v in providers.items()},
        "net_receivers": {e: round(float(v), 2) for e, v in receivers.items()},
        "total_provided": round(total_provided, 2),
        "balanced": bool(abs(net_sum) < 1e-6),
    }


def funding_cost_analysis(
    funding_amounts: np.ndarray,
    funding_rates: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Weighted-average funding cost.

    Computes the amount-weighted average cost of the funding base and the total
    annual funding cost in currency terms.

    Args:
        funding_amounts: Outstanding amount of each funding source.
        funding_rates: Annual rate (decimal) per source, e.g. 0.035 for 3.5%.

    Returns:
        Dict with ``weighted_avg_cost`` (decimal), ``total_annual_cost`` and
        ``total_funding``.

    Raises:
        ValueError: If lengths differ or total funding is zero.
    """
    amounts = np.asarray(funding_amounts, dtype=np.float64)
    rates = np.asarray(funding_rates, dtype=np.float64)
    if amounts.shape != rates.shape:
        raise ValueError("funding_amounts and funding_rates must have equal length")
    total = float(np.sum(amounts))
    if total == 0:
        raise ValueError("total funding must be positive")
    total_cost = float(np.sum(amounts * rates))
    wac = total_cost / total
    return {
        "weighted_avg_cost": round(wac, 8),
        "total_annual_cost": round(total_cost, 2),
        "total_funding": round(total, 2),
    }


def liquidity_transfer_pricing(
    notional: float,
    tenor_years: float,
    base_rate: float,
    liquidity_spread: float,
    contingent_spread: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """Liquidity Transfer Pricing (LTP) charge for a funding position.

    The FTP charge passes the cost of liquidity to business lines: the all-in
    transfer rate is ``base_rate + term liquidity premium + contingent liquidity
    premium``. The annual charge is that rate applied to notional; the lifetime
    charge multiplies by tenor.

    Args:
        notional: Position notional being funded.
        tenor_years: Funding tenor in years (>= 0).
        base_rate: Reference/base funding rate (decimal).
        liquidity_spread: Term liquidity premium (decimal).
        contingent_spread: Contingent liquidity premium for undrawn/optional
            commitments (decimal).

    Returns:
        Dict with ``all_in_rate``, ``annual_charge`` and ``lifetime_charge``.

    Raises:
        ValueError: If notional is negative or tenor is negative.
    """
    if notional < 0 or tenor_years < 0:
        raise ValueError("notional and tenor_years must be non-negative")
    all_in = base_rate + liquidity_spread + contingent_spread
    annual = notional * all_in
    lifetime = annual * tenor_years
    return {
        "all_in_rate": round(float(all_in), 8),
        "annual_charge": round(float(annual), 2),
        "lifetime_charge": round(float(lifetime), 2),
    }

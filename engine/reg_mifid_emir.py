"""engine/reg_mifid_emir.py — MiFID II, EMIR and SFTR compliance.

Implements the MiFID II and EMIR & SFTR regulatory sub-domains:
  * MiFID II: transaction report validator, pre-/post-trade transparency,
    best-execution metric, algorithm documentation completeness.
  * EMIR: trade repository report builder, clearing obligation check, margin
    requirement (initial + variation).
  * SFTR: securities-financing transaction report builder.

These are validation / reporting functions. They return the convention
documented in the regulatory skill: ``{"valid": bool, "errors": list,
"report": dict}`` for validators. Pure typed Python/NumPy — no @njit (no array
hot loops; logic is field validation and aggregation).

References: MiFIR (Regulation (EU) 600/2014); RTS 22/1/2; EMIR (Regulation (EU)
648/2012) Art. 4, 11; SFTR (Regulation (EU) 2015/2365).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "mifid_ii_transaction_report_validator",
    "mifid_ii_pre_trade_transparency",
    "mifid_ii_post_trade_transparency",
    "mifid_ii_best_execution_metric",
    "mifid_ii_algorithm_documentation",
    "emir_trade_repository_report",
    "emir_clearing_obligation_check",
    "emir_margin_requirement",
    "sftr_securities_finance_report",
]

# RTS 22 mandatory transaction-report fields (representative core subset).
_MIFID_TXN_REQUIRED_FIELDS: tuple[str, ...] = (
    "transaction_reference_number",
    "executing_entity_lei",
    "buyer_id",
    "seller_id",
    "instrument_isin",
    "price",
    "quantity",
    "trading_datetime",
    "venue",
)


def mifid_ii_transaction_report_validator(
    report: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """MiFID II / RTS 22 transaction report field validator.

    Checks the presence and basic validity of the mandatory transaction-report
    fields (LEI length, ISIN length, positive price/quantity).

    Args:
        report: Mapping of transaction-report field names to values.

    Returns:
        Dict ``{"valid": bool, "errors": list[str], "report": dict}``.
    """
    errors: list[str] = []
    for field in _MIFID_TXN_REQUIRED_FIELDS:
        if field not in report or report[field] in (None, ""):
            errors.append(f"missing_required_field:{field}")

    lei = str(report.get("executing_entity_lei", ""))
    if lei and len(lei) != 20:
        errors.append("invalid_lei_length")
    isin = str(report.get("instrument_isin", ""))
    if isin and len(isin) != 12:
        errors.append("invalid_isin_length")
    try:
        if "price" in report and float(report["price"]) <= 0.0:
            errors.append("non_positive_price")
        if "quantity" in report and float(report["quantity"]) <= 0.0:
            errors.append("non_positive_quantity")
    except (TypeError, ValueError):
        errors.append("non_numeric_price_or_quantity")

    return {"valid": len(errors) == 0, "errors": errors, "report": report}


def mifid_ii_pre_trade_transparency(
    instrument_type: str,
    order_size: float,
    large_in_scale_threshold: float,
    is_liquid: bool = True,
) -> dict:  # type: ignore[type-arg]
    """MiFID II pre-trade transparency / LIS waiver assessment.

    Determines whether an order qualifies for the Large-in-Scale (LIS) waiver
    from pre-trade transparency (illiquid instruments and orders above the LIS
    threshold may be waived).

    Args:
        instrument_type: Instrument class label (informational).
        order_size: Order size in the relevant unit (notional/quantity).
        large_in_scale_threshold: LIS threshold for the instrument.
        is_liquid: Whether the instrument has a liquid market.

    Returns:
        Dict with ``transparency_required`` (bool), ``waiver`` (str | None) and
        the ``instrument_type``.

    Raises:
        ValueError: If sizes are negative.
    """
    if order_size < 0.0 or large_in_scale_threshold < 0.0:
        raise ValueError("sizes must be non-negative")
    waiver: str | None = None
    if order_size >= large_in_scale_threshold:
        waiver = "large_in_scale"
    elif not is_liquid:
        waiver = "illiquid_instrument"
    return {
        "transparency_required": waiver is None,
        "waiver": waiver,
        "instrument_type": instrument_type,
    }


def mifid_ii_post_trade_transparency(
    trade_size: float,
    delayed_publication_threshold: float,
    is_liquid: bool = True,
) -> dict:  # type: ignore[type-arg]
    """MiFID II post-trade transparency / deferred-publication assessment.

    Trades above the size threshold (or in illiquid instruments) may benefit
    from deferred publication; otherwise publication is near real-time.

    Args:
        trade_size: Executed trade size (notional/quantity).
        delayed_publication_threshold: Size threshold for deferral.
        is_liquid: Whether the instrument has a liquid market.

    Returns:
        Dict with ``publication`` ("real_time" | "deferred") and
        ``deferral_eligible``.

    Raises:
        ValueError: If sizes are negative.
    """
    if trade_size < 0.0 or delayed_publication_threshold < 0.0:
        raise ValueError("sizes must be non-negative")
    deferral = trade_size >= delayed_publication_threshold or not is_liquid
    return {
        "publication": "deferred" if deferral else "real_time",
        "deferral_eligible": bool(deferral),
    }


def mifid_ii_best_execution_metric(
    executed_prices: np.ndarray,
    benchmark_prices: np.ndarray,
    quantities: np.ndarray,
    side: int = 1,
) -> dict:  # type: ignore[type-arg]
    """MiFID II RTS 27/28 best-execution metric.

    Computes the quantity-weighted price improvement (or slippage) of executions
    versus a reference (e.g. EBBO) price, in basis points. Positive means price
    improvement for the client.

    Args:
        executed_prices: Executed price per fill.
        benchmark_prices: Reference (EBBO/arrival) price per fill.
        quantities: Executed quantity per fill.
        side: +1 for buys, -1 for sells.

    Returns:
        Dict with ``price_improvement_bps`` (quantity-weighted),
        ``fill_rate`` (fraction with non-negative improvement) and ``n_fills``.

    Raises:
        ValueError: If arrays differ in length, are empty, or side invalid.
    """
    p = np.asarray(executed_prices, dtype=np.float64)
    bench = np.asarray(benchmark_prices, dtype=np.float64)
    q = np.asarray(quantities, dtype=np.float64)
    if p.size == 0 or not (p.size == bench.size == q.size):
        raise ValueError("price/quantity arrays must be non-empty and equal length")
    if side not in (1, -1):
        raise ValueError("side must be +1 (buy) or -1 (sell)")

    # Improvement positive when buying below / selling above the benchmark.
    improvement = side * (bench - p)
    total_qty = float(np.sum(q))
    weighted_ref = float(np.sum(bench * q))
    improvement_bps = (
        float(np.sum(improvement * q)) / weighted_ref * 1e4 if weighted_ref > 0.0 else 0.0
    )
    fill_rate = float(np.mean(improvement >= 0.0))
    return {
        "price_improvement_bps": round(improvement_bps, 6),
        "fill_rate": round(fill_rate, 6),
        "total_quantity": round(total_qty, 6),
        "n_fills": int(p.size),
    }


def mifid_ii_algorithm_documentation(
    documentation: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """MiFID II RTS 6 algorithmic-trading documentation completeness check.

    Verifies that the mandatory governance and control documentation items for
    an algorithmic trading strategy are present.

    Args:
        documentation: Mapping of documentation item -> provided (bool/value).

    Returns:
        Dict ``{"valid": bool, "errors": list[str], "report": dict}`` where
        errors list the missing mandatory items.
    """
    required = (
        "strategy_description",
        "risk_controls",
        "kill_switch",
        "testing_evidence",
        "deployment_signoff",
        "monitoring_arrangements",
    )
    errors = [f"missing:{item}" for item in required if not documentation.get(item)]
    completeness = 1.0 - len(errors) / len(required)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "report": {"completeness": round(completeness, 4)},
    }


def emir_trade_repository_report(
    trade: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """EMIR trade repository report builder/validator.

    Validates the core EMIR reporting fields (counterparty LEIs, UTI, notional,
    asset class) and echoes a normalised report.

    Args:
        trade: Mapping of EMIR trade fields to values.

    Returns:
        Dict ``{"valid": bool, "errors": list[str], "report": dict}``.
    """
    required = (
        "reporting_counterparty_lei",
        "other_counterparty_lei",
        "uti",
        "asset_class",
        "notional",
        "execution_timestamp",
    )
    errors = [f"missing:{f}" for f in required if trade.get(f) in (None, "")]
    for lei_field in ("reporting_counterparty_lei", "other_counterparty_lei"):
        val = str(trade.get(lei_field, ""))
        if val and len(val) != 20:
            errors.append(f"invalid_lei:{lei_field}")
    try:
        if "notional" in trade and float(trade["notional"]) <= 0.0:
            errors.append("non_positive_notional")
    except (TypeError, ValueError):
        errors.append("non_numeric_notional")
    return {"valid": len(errors) == 0, "errors": errors, "report": trade}


def emir_clearing_obligation_check(
    notionals: dict,  # type: ignore[type-arg]
    counterparty_category: str,
    clearing_thresholds: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """EMIR clearing obligation check (Art. 4 / Art. 4a / Art. 10 / clearing thresholds).

    [REGULATORY] EMIR REFIT (Regulation (EU) 2019/834) Art. 4a(1): a Financial
    Counterparty (FC) that breaches its clearing threshold in ANY ONE OTC
    derivative asset class becomes subject to the clearing obligation for ALL
    asset classes it has positions in, not just the one that breached. Art.
    10(1) evaluates a Non-Financial Counterparty above threshold (NFC+)
    per-asset-class instead -- only the classes where ITS OWN threshold is
    breached become subject to clearing.

    A prior version of this function applied FC's per-class-only logic to
    BOTH categories (took a single ``asset_class``/``notional`` pair,
    identical branching for FC and NFC+ beyond the NFC- exemption). It
    understated an FC's clearing scope whenever the breaching class differed
    from the queried class -- masked in the original test, which happened to
    query the same class that breached. Found during the Tier 3 #2 audit.

    Args:
        notionals: Mapping asset_class -> gross notional outstanding for this
            counterparty, across ALL asset classes it holds positions in.
            Required (not just the one class being asked about) for the FC
            any-class-breach rule: a single class's notional alone cannot
            answer whether the FC-wide obligation applies.
        counterparty_category: One of "FC", "NFC+", "NFC-".
        clearing_thresholds: Mapping asset_class -> clearing threshold notional.

    Returns:
        Dict with ``clearing_required`` (mapping asset_class -> bool, one
        entry per class in ``notionals``), ``any_class_breached`` (bool --
        the FC any-class trigger) and the ``counterparty_category``.

    Raises:
        ValueError: If any notional is negative or category unknown.
    """
    if counterparty_category not in ("FC", "NFC+", "NFC-"):
        raise ValueError("counterparty_category must be FC, NFC+ or NFC-")
    if any(float(notional) < 0.0 for notional in notionals.values()):
        raise ValueError("notional must be non-negative")

    if counterparty_category == "NFC-":
        return {
            "clearing_required": {ac: False for ac in notionals},
            "any_class_breached": False,
            "counterparty_category": counterparty_category,
        }

    breaches = {
        ac: float(notional) > float(clearing_thresholds.get(ac, float("inf")))
        for ac, notional in notionals.items()
    }
    any_breached = any(breaches.values())

    if counterparty_category == "FC":
        # Art. 4a(1): ANY breach -> clearing required across ALL classes.
        clearing_required = {ac: any_breached for ac in notionals}
    else:  # NFC+
        # Art. 10(1): per-class only.
        clearing_required = dict(breaches)

    return {
        "clearing_required": clearing_required,
        "any_class_breached": bool(any_breached),
        "counterparty_category": counterparty_category,
    }


def emir_margin_requirement(
    portfolio_value: float,
    initial_margin_rate: float,
    variation_margin: float,
    minimum_transfer_amount: float = 0.0,
) -> dict:  # type: ignore[type-arg]
    """EMIR (Art. 11) uncleared-derivatives margin requirement.

    Computes the Initial Margin (IM) from the rate and the net margin call after
    applying the Minimum Transfer Amount (MTA) to the variation margin.

    Args:
        portfolio_value: Gross portfolio value / notional for IM scaling.
        initial_margin_rate: IM as a fraction of portfolio value.
        variation_margin: Net mark-to-market variation margin owed.
        minimum_transfer_amount: MTA below which no transfer is made.

    Returns:
        Dict with ``initial_margin``, ``variation_margin_call`` (after MTA) and
        ``total_margin``.

    Raises:
        ValueError: If the IM rate is negative or portfolio value negative.
    """
    if portfolio_value < 0.0 or initial_margin_rate < 0.0:
        raise ValueError("portfolio_value and initial_margin_rate must be non-negative")
    im = initial_margin_rate * portfolio_value
    vm_call = variation_margin if abs(variation_margin) >= minimum_transfer_amount else 0.0
    return {
        "initial_margin": round(im, 4),
        "variation_margin_call": round(vm_call, 4),
        "total_margin": round(im + vm_call, 4),
    }


def sftr_securities_finance_report(
    transaction: dict,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    """SFTR securities-financing transaction report builder/validator.

    Validates the core SFTR fields for an SFT (repo, securities lending, buy-
    sell back, margin lending): counterparties, UTI, collateral and the SFT
    type.

    Args:
        transaction: Mapping of SFTR fields to values.

    Returns:
        Dict ``{"valid": bool, "errors": list[str], "report": dict}``.
    """
    required = (
        "reporting_counterparty_lei",
        "other_counterparty_lei",
        "uti",
        "sft_type",
        "principal_amount",
        "collateral_value",
    )
    valid_types = {"repo", "securities_lending", "buy_sell_back", "margin_lending"}
    errors = [f"missing:{f}" for f in required if transaction.get(f) in (None, "")]
    sft_type = transaction.get("sft_type")
    if sft_type and sft_type not in valid_types:
        errors.append("invalid_sft_type")
    try:
        if "collateral_value" in transaction and float(transaction["collateral_value"]) < 0.0:
            errors.append("negative_collateral_value")
    except (TypeError, ValueError):
        errors.append("non_numeric_collateral_value")
    return {"valid": len(errors) == 0, "errors": errors, "report": transaction}

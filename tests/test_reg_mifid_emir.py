"""tests/test_reg_mifid_emir.py — numerical-correctness tests.

No mocking (CLAUDE.md §5 RULE 1). Tests assert validator pass/fail on
field presence and validity, LIS/deferral logic, best-execution sign, clearing
threshold logic, EMIR margin + MTA, and SFTR validation.
"""

import numpy as np

from engine.reg_mifid_emir import (
    emir_clearing_obligation_check,
    emir_margin_requirement,
    emir_trade_repository_report,
    mifid_ii_algorithm_documentation,
    mifid_ii_best_execution_metric,
    mifid_ii_post_trade_transparency,
    mifid_ii_pre_trade_transparency,
    mifid_ii_transaction_report_validator,
    sftr_securities_finance_report,
)


def _valid_txn():
    return {
        "transaction_reference_number": "TXN1",
        "executing_entity_lei": "5493000IBP32UQZ0KL24",
        "buyer_id": "B1",
        "seller_id": "S1",
        "instrument_isin": "GB00B03MLX29",
        "price": 101.5,
        "quantity": 100,
        "trading_datetime": "2026-06-11T10:00:00Z",
        "venue": "XLON",
    }


# ── MiFID transaction validator ───────────────────────────────────────────────


def test_txn_validator_passes_valid():
    r = mifid_ii_transaction_report_validator(_valid_txn())
    assert r["valid"] is True
    assert r["errors"] == []


def test_txn_validator_flags_missing_and_bad_lei():
    bad = _valid_txn()
    del bad["venue"]
    bad["executing_entity_lei"] = "TOOSHORT"
    bad["price"] = -1.0
    r = mifid_ii_transaction_report_validator(bad)
    assert r["valid"] is False
    assert "missing_required_field:venue" in r["errors"]
    assert "invalid_lei_length" in r["errors"]
    assert "non_positive_price" in r["errors"]


# ── Pre/post trade transparency ───────────────────────────────────────────────


def test_pre_trade_lis_waiver():
    r = mifid_ii_pre_trade_transparency("equity", order_size=1e6, large_in_scale_threshold=5e5)
    assert r["waiver"] == "large_in_scale"
    assert r["transparency_required"] is False


def test_pre_trade_illiquid_waiver():
    r = mifid_ii_pre_trade_transparency(
        "bond", order_size=100.0, large_in_scale_threshold=5e5, is_liquid=False
    )
    assert r["waiver"] == "illiquid_instrument"


def test_post_trade_deferred():
    r = mifid_ii_post_trade_transparency(trade_size=1e6, delayed_publication_threshold=5e5)
    assert r["publication"] == "deferred"


def test_post_trade_real_time():
    r = mifid_ii_post_trade_transparency(trade_size=100.0, delayed_publication_threshold=5e5)
    assert r["publication"] == "real_time"


# ── Best execution ────────────────────────────────────────────────────────────


def test_best_execution_price_improvement_on_buy_below_benchmark():
    r = mifid_ii_best_execution_metric(
        executed_prices=np.array([99.0, 99.5]),
        benchmark_prices=np.array([100.0, 100.0]),
        quantities=np.array([10.0, 10.0]),
        side=1,
    )
    assert r["price_improvement_bps"] > 0
    assert r["fill_rate"] == 1.0


# ── Algorithm documentation ───────────────────────────────────────────────────


def test_algo_doc_complete():
    doc = {
        "strategy_description": True,
        "risk_controls": True,
        "kill_switch": True,
        "testing_evidence": True,
        "deployment_signoff": True,
        "monitoring_arrangements": True,
    }
    r = mifid_ii_algorithm_documentation(doc)
    assert r["valid"] is True
    assert r["report"]["completeness"] == 1.0


def test_algo_doc_incomplete():
    r = mifid_ii_algorithm_documentation({"strategy_description": True})
    assert r["valid"] is False
    assert r["report"]["completeness"] < 1.0


# ── EMIR ──────────────────────────────────────────────────────────────────────


def test_emir_trade_report_valid():
    trade = {
        "reporting_counterparty_lei": "5493000IBP32UQZ0KL24",
        "other_counterparty_lei": "5493000IBP32UQZ0KL24",
        "uti": "UTI123",
        "asset_class": "interest_rate",
        "notional": 1e6,
        "execution_timestamp": "2026-06-11T09:00:00Z",
    }
    assert emir_trade_repository_report(trade)["valid"] is True


def test_emir_clearing_required_for_fc_above_threshold():
    r = emir_clearing_obligation_check(
        "interest_rate",
        notional=5e9,
        counterparty_category="FC",
        clearing_thresholds={"interest_rate": 3e9},
    )
    assert r["clearing_required"] is True


def test_emir_clearing_not_required_for_nfc_minus():
    r = emir_clearing_obligation_check(
        "credit", notional=1e12, counterparty_category="NFC-", clearing_thresholds={"credit": 1e9}
    )
    assert r["clearing_required"] is False


def test_emir_margin_mta_suppresses_small_vm():
    r = emir_margin_requirement(
        portfolio_value=1e6,
        initial_margin_rate=0.05,
        variation_margin=100.0,
        minimum_transfer_amount=500.0,
    )
    assert r["initial_margin"] == 50000.0
    assert r["variation_margin_call"] == 0.0  # below MTA


# ── SFTR ──────────────────────────────────────────────────────────────────────


def test_sftr_valid():
    txn = {
        "reporting_counterparty_lei": "5493000IBP32UQZ0KL24",
        "other_counterparty_lei": "5493000IBP32UQZ0KL24",
        "uti": "SFT1",
        "sft_type": "repo",
        "principal_amount": 1e6,
        "collateral_value": 1.02e6,
    }
    assert sftr_securities_finance_report(txn)["valid"] is True


def test_sftr_invalid_type():
    txn = {
        "reporting_counterparty_lei": "5493000IBP32UQZ0KL24",
        "other_counterparty_lei": "5493000IBP32UQZ0KL24",
        "uti": "SFT1",
        "sft_type": "swap",
        "principal_amount": 1e6,
        "collateral_value": 1e6,
    }
    r = sftr_securities_finance_report(txn)
    assert r["valid"] is False
    assert "invalid_sft_type" in r["errors"]

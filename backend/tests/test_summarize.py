from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from backend import db
from backend.llm.summarize import compute_summary_stats, detect_recurring_charges
from backend.models import Transaction


def _tx(desc: str, merchant: str, date_str: str, amount: Decimal, *, is_transfer: bool = False) -> Transaction:
    return Transaction(
        id=db.make_transaction_id("checking", date_str, desc, amount),
        date=date_str, description=desc, merchant=merchant, merchant_normalized=merchant.lower(),
        amount=amount, account="checking", source_file="s.csv", extraction_method="csv",
        category="Dining & Takeout" if amount < 0 else "Income", is_transfer=is_transfer,
    )


def test_compute_summary_stats_basic_totals(db_path: Path) -> None:
    file_id = db.insert_file(
        db_path, path="/tmp/s.csv", filename="s.csv", size_bytes=1, mtime=0.0, sha256="h", file_type="csv"
    )
    txs = [
        _tx("A", "Starbucks", "2026-08-01", Decimal("-5.00")),
        _tx("B", "Whole Foods", "2026-08-02", Decimal("-80.00")),
        _tx("C", "Paycheck", "2026-08-03", Decimal("2000.00")),
        _tx("D", "Internal Transfer", "2026-08-04", Decimal("-500.00"), is_transfer=True),
    ]
    db.insert_transactions(db_path, file_id, txs)

    stats = compute_summary_stats(db_path, "2026-08")

    assert stats["total_out"] == Decimal("85.00")  # transfer excluded
    assert stats["total_in"] == Decimal("2000.00")
    assert stats["net"] == Decimal("1915.00")
    assert stats["transaction_count"] == 3  # transfer excluded from count too


def test_detect_recurring_charges_same_amount_twice() -> None:
    txs = [
        _tx("Netflix", "Netflix", "2026-07-01", Decimal("-15.49")),
        _tx("Netflix", "Netflix", "2026-08-01", Decimal("-15.49")),
    ]
    recurring = detect_recurring_charges(txs)
    assert len(recurring) == 1
    assert recurring[0].merchant == "Netflix"
    assert recurring[0].amount == Decimal("15.49")
    assert recurring[0].occurrences == 2


def test_detect_recurring_charges_ignores_one_off() -> None:
    txs = [_tx("One Time Purchase", "Random Shop", "2026-08-01", Decimal("-40.00"))]
    assert detect_recurring_charges(txs) == []


def test_detect_recurring_charges_variable_amount_across_months() -> None:
    txs = [
        _tx("Electric Bill", "City Power", "2026-06-15", Decimal("-60.00")),
        _tx("Electric Bill", "City Power", "2026-07-15", Decimal("-75.00")),
        _tx("Electric Bill", "City Power", "2026-08-15", Decimal("-68.00")),
    ]
    recurring = detect_recurring_charges(txs)
    assert len(recurring) == 1
    assert recurring[0].merchant == "City Power"
    assert recurring[0].amount is None  # varies, so no single amount
    assert recurring[0].occurrences == 3

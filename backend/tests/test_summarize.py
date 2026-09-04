from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from backend import db
from backend.llm.summarize import compute_summary_stats
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
